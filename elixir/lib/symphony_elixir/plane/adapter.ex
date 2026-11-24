defmodule SymphonyElixir.Plane.Adapter do
  @moduledoc "Project-scoped Plane CE v1 tracker. Tool writes are bound to the running card."
  @behaviour SymphonyElixir.Tracker
  alias SymphonyElixir.{Config, Tracker.Issue}

  @impl true
  def secret_environment_names(_), do: ["PLANE_API_KEY"]

  @impl true
  def validate_config(%{active_states: [_ | _], terminal_states: [_ | _]} = settings) do
    with {:ok, _} <- connection(settings), do: :ok
  end

  def validate_config(_), do: {:error, :missing_plane_states}

  @impl true
  def fetch_issues_by_states([]), do: {:ok, []}

  def fetch_issues_by_states(states) do
    with {:ok, conn} <- connection(Config.settings!().tracker),
         {:ok, rows} <- pages(conn, "work-items/", expand: "state,labels"),
         {:ok, items} <- collect(rows, &issue/1) do
      {:ok,
       Enum.filter(items, fn item ->
         Enum.any?(states, &(String.downcase(&1) == String.downcase(item.state)))
       end)}
    end
  end

  @impl true
  def fetch_issues_by_ids([]), do: {:ok, []}

  def fetch_issues_by_ids(ids) do
    with {:ok, conn} <- connection(Config.settings!().tracker) do
      collect(Enum.uniq(ids), &fetch_item(conn, &1))
    end
  end

  defp fetch_item(conn, id) do
    case request(conn, :get, "work-items/#{id}/", params: [expand: "state,labels"]) do
      {:ok, row} -> issue(row)
      {:error, {:plane_http, 404}} -> :skip
      error -> error
    end
  end

  @spec issue(term()) :: {:ok, Issue.t()} | {:error, atom()}
  def issue(%{"id" => id, "name" => name, "state" => %{"name" => state}, "sequence_id" => seq} = row)
      when is_binary(id) and is_binary(name) and is_binary(state) and is_integer(seq) do
    {:ok,
     %Issue{
       id: id,
       identifier: "PL-#{seq}",
       title: name,
       state: state,
       description: row["description_stripped"] || row["description_html"],
       priority: %{"urgent" => 1, "high" => 2, "medium" => 3, "low" => 4}[row["priority"]],
       labels: for(%{"name" => label} <- row["labels"] || [], do: label),
       created_at: date(row["created_at"]),
       updated_at: date(row["updated_at"]),
       dispatchable: true
     }}
  end

  def issue(_), do: {:error, :invalid_plane_item}

  defp date(value) when is_binary(value) do
    case DateTime.from_iso8601(value) do
      {:ok, date, _} -> date
      _ -> nil
    end
  end

  defp date(_), do: nil

  @impl true
  def agent_tool_specs do
    [
      %{
        "name" => "plane_card",
        "description" => "Read comments, post a plain-text comment, or move this card to a named state.",
        "inputSchema" => %{
          "type" => "object",
          "additionalProperties" => false,
          "required" => ["action"],
          "properties" => %{
            "action" => %{"type" => "string", "enum" => ["comments", "comment", "move"]},
            "value" => %{"type" => "string"}
          }
        }
      }
    ]
  end

  @impl true
  def execute_agent_tool(tool, args, opts) do
    result =
      with "plane_card" <- tool,
           %{id: id} <- opts[:issue],
           {:ok, conn} <- connection(opts[:tracker_settings]) do
        card_action(conn, "work-items/#{id}/", args, opts)
      else
        _ -> {:error, :invalid_plane_tool_context}
      end

    {status, data} = result
    output = if status == :ok, do: Jason.encode!(data), else: inspect(data)

    %{
      "success" => status == :ok,
      "output" => output,
      "contentItems" => [%{"type" => "inputText", "text" => output}]
    }
  end

  defp card_action({base, _token} = conn, path, %{"action" => "move", "value" => name} = args, opts) when is_binary(name) do
    provider = opts[:tracker_settings].provider

    state = name |> String.trim() |> String.downcase()

    with :ok <- prepare_landing(state, provider, opts[:issue], base <> path),
         :ok <- publish_review_images(state, provider, opts[:issue], base <> path) do
      action(conn, path, args)
    end
  end

  defp card_action(conn, path, args, _opts), do: action(conn, path, args)

  defp prepare_landing("approved", %{"landing" => _}, _, _), do: {:error, :approval_requires_reviewer}

  defp prepare_landing(state, %{"landing" => settings}, issue, card_url) when state in ["review", "done"] do
    args = ["-I", settings["script"], settings["profile"], issue.identifier, card_url, state]

    case System.cmd("python3", args, stderr_to_stdout: true) do
      {_, 0} -> :ok
      {message, _} -> {:error, {:landing, String.trim(message)}}
    end
  end

  defp prepare_landing(_, _, _, _), do: :ok

  defp publish_review_images("review", %{"review_image_script" => script, "url" => origin}, issue, card_url) do
    args = ["-I", script, Config.settings!().workspace.root, issue.identifier, card_url, origin]

    case System.cmd("python3", args, stderr_to_stdout: true) do
      {_, 0} -> :ok
      {message, _} -> {:error, {:review_images, String.trim(message)}}
    end
  end

  defp publish_review_images(_, _, _, _), do: :ok

  defp action(conn, path, %{"action" => "comments"}), do: pages(conn, path <> "comments/", [])

  defp action(conn, path, %{"action" => "comment", "value" => text})
       when is_binary(text) and text != "" do
    html = Phoenix.HTML.html_escape(text) |> Phoenix.HTML.safe_to_string()
    request(conn, :post, path <> "comments/", json: %{comment_html: "<pre>#{html}</pre>"})
  end

  defp action(conn, path, %{"action" => "move", "value" => name}) when is_binary(name) do
    with {:ok, states} <- pages(conn, "states/", []),
         [%{"id" => id}] <-
           Enum.filter(states, &(String.downcase(&1["name"]) == String.downcase(name))) do
      request(conn, :patch, path, json: %{state: id})
    else
      {:error, _} = error -> error
      _ -> {:error, :unknown_or_ambiguous_plane_state}
    end
  end

  defp action(_, _, _), do: {:error, :invalid_plane_action}

  defp connection(%{provider: %{"url" => url, "workspace" => slug, "project_id" => project}})
       when is_binary(url) do
    token = System.get_env("PLANE_API_KEY")

    cond do
      not valid_url?(URI.parse(url)) ->
        {:error, :invalid_plane_url}

      !is_binary(slug) or !Regex.match?(~r/^[a-z0-9_-]+$/i, slug) ->
        {:error, :invalid_plane_workspace}

      !is_binary(project) or !match?({:ok, _}, Ecto.UUID.cast(project)) ->
        {:error, :invalid_plane_project}

      token in [nil, ""] ->
        {:error, :missing_plane_token}

      true ->
        {:ok, {String.trim_trailing(url, "/") <> "/api/v1/workspaces/#{slug}/projects/#{project}/", token}}
    end
  end

  defp connection(_), do: {:error, :missing_plane_settings}

  defp valid_url?(%URI{host: host, scheme: scheme, userinfo: nil, query: nil, fragment: nil}) when is_binary(host) do
    scheme == "https" or (scheme == "http" and host in ["localhost", "127.0.0.1", "::1"])
  end

  defp valid_url?(_uri), do: false

  defp pages(conn, path, params, seen \\ %{}, acc \\ []) do
    case request(conn, :get, path, params: params) do
      {:ok, %{"results" => rows, "next_page_results" => false}} when is_list(rows) ->
        {:ok, Enum.reverse([rows | acc]) |> List.flatten()}

      {:ok, %{"results" => rows, "next_page_results" => true, "next_cursor" => cursor}}
      when is_list(rows) and is_binary(cursor) ->
        if Map.has_key?(seen, cursor) do
          {:error, :repeated_plane_cursor}
        else
          pages(conn, path, Keyword.put(params, :cursor, cursor), Map.put(seen, cursor, true), [rows | acc])
        end

      {:ok, _} ->
        {:error, :invalid_plane_page}

      error ->
        error
    end
  end

  defp collect(values, fun) do
    Enum.reduce_while(values, {:ok, []}, fn value, {:ok, acc} ->
      case fun.(value) do
        {:ok, item} -> {:cont, {:ok, [item | acc]}}
        :skip -> {:cont, {:ok, acc}}
        error -> {:halt, error}
      end
    end)
    |> then(fn
      {:ok, items} -> {:ok, Enum.reverse(items)}
      error -> error
    end)
  end

  defp request({base, token}, method, path, opts) do
    case Req.request(
           [
             url: base <> path,
             method: method,
             headers: [{"x-api-key", token}],
             redirect: false,
             retry: false
           ] ++ opts
         ) do
      {:ok, %{status: status, body: body}} when status in 200..299 -> {:ok, body}
      {:ok, %{status: status}} -> {:error, {:plane_http, status}}
      {:error, _} -> {:error, :plane_unreachable}
    end
  end
end
