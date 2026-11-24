defmodule SymphonyElixir.Plane.QueueTest do
  use SymphonyElixir.TestSupport

  test "dispatches only eligible cards, binds writes to the current card, and reuses its identity after review" do
    original = System.get_env("PLANE_API_KEY")
    System.put_env("PLANE_API_KEY", "test-key")
    on_exit(fn -> restore_env("PLANE_API_KEY", original) end)
    parent = self()
    project = Ecto.UUID.generate()
    prefix = "/api/v1/workspaces/books/projects/#{project}/"
    {:ok, store} = Agent.start_link(fn -> "Ready" end)
    row = fn id, seq, state -> %{"id" => id, "name" => id, "state" => %{"name" => state}, "sequence_id" => seq} end
    page = fn rows -> %{"results" => rows, "next_page_results" => false} end

    plug = fn conn, _ ->
      assert Plug.Conn.get_req_header(conn, "x-api-key") == ["test-key"]
      conn = Plug.Conn.fetch_query_params(conn)
      path = String.replace_prefix(conn.request_path, prefix, "")

      {status, body} =
        case {conn.method, path} do
          {"GET", "work-items/"} ->
            if conn.query_params["cursor"] == "next" do
              {200, page.([row.("two", 2, "Review"), row.("three", 3, "Ready")])}
            else
              {200, %{"results" => [row.("one", 1, Agent.get(store, & &1))], "next_page_results" => true, "next_cursor" => "next"}}
            end

          {"GET", "work-items/one/"} ->
            {200, row.("one", 1, Agent.get(store, & &1))}

          {"GET", "work-items/forbidden/"} ->
            {403, %{}}

          {"GET", "work-items/broken/comments/"} ->
            {200, %{}}

          {"GET", "work-items/repeated/comments/"} ->
            {200, %{"results" => [], "next_page_results" => true, "next_cursor" => "same"}}

          {"GET", "work-items/missing/"} ->
            {404, %{}}

          {"GET", "states/"} ->
            {200, page.([%{"id" => "review", "name" => "Review"}])}

          {"PATCH", "work-items/one/"} ->
            {:ok, body, _} = Plug.Conn.read_body(conn)
            assert Jason.decode!(body) == %{"state" => "review"}
            Agent.update(store, fn _ -> "Review" end)
            {200, %{}}

          {"POST", "work-items/one/comments/"} ->
            {:ok, body, _} = Plug.Conn.read_body(conn)
            send(parent, {:comment, Jason.decode!(body)})
            {201, %{}}

          {"GET", "work-items/one/comments/"} ->
            {200, page.([%{"comment_html" => "Revise the mobile layout"}])}
        end

      conn |> Plug.Conn.put_resp_content_type("application/json") |> Plug.Conn.send_resp(status, Jason.encode!(body))
    end

    endpoint = {Bandit, plug: plug, ip: {127, 0, 0, 1}, port: 0}
    server = start_supervised!(Supervisor.child_spec(endpoint, id: :plane_api))
    {:ok, {_, port}} = ThousandIsland.listener_info(server)
    provider = %{url: "http://127.0.0.1:#{port}", workspace: "books", project_id: project}
    settings = %{kind: "plane", provider: provider, active_states: ["Ready", "In progress"], terminal_states: ["Done"]}
    File.write!(Workflow.workflow_file_path(), "---\n" <> Jason.encode!(%{tracker: settings}) <> "\n---\nWork on {{ issue.identifier }}")
    assert :ok = Config.validate!()
    assert {:ok, [%Issue{id: "one"} = card, %Issue{id: "three"}]} = Tracker.fetch_issues_by_states(["Ready"])
    drain_path = Path.join(Path.dirname(Workflow.workflow_file_path()), "drain")
    original_drain = System.get_env("SYMPHONY_DRAIN_FILE")
    System.put_env("SYMPHONY_DRAIN_FILE", drain_path)
    on_exit(fn -> restore_env("SYMPHONY_DRAIN_FILE", original_drain) end)
    scheduler = %Orchestrator.State{max_concurrent_agents: 1}
    assert Orchestrator.should_dispatch_issue_for_test(card, scheduler)
    File.touch!(drain_path)
    refute Orchestrator.should_dispatch_issue_for_test(card, scheduler)

    binding = Tracker.bind_agent_tools()
    assert "PLANE_API_KEY" in binding.secret_environment_names
    call = fn args -> Tracker.execute_bound_agent_tool(binding, "plane_card", args, issue: card) end
    assert call.(%{"action" => "comment", "value" => "see <draft>"})["success"]
    assert_receive {:comment, %{"comment_html" => "<pre>see &lt;draft&gt;</pre>"}}
    assert call.(%{"action" => "move", "value" => "Review"})["success"]
    assert {:ok, [%Issue{id: "three"}]} = Tracker.fetch_issues_by_states(["Ready"])
    assert {:ok, [%Issue{state: "Review"}]} = Tracker.fetch_issues_by_ids(["one", "missing"])
    Agent.update(store, fn _ -> "Ready" end)
    assert {:ok, [^card]} = Tracker.fetch_issues_by_ids(["one"])
    assert call.(%{"action" => "comments"})["output"] =~ "Revise the mobile layout"
    refute call.(%{"action" => "move", "value" => "unknown"})["success"]
    refute call.(%{"action" => "delete"})["success"]
    assert {:error, {:plane_http, 403}} = Tracker.fetch_issues_by_ids(["forbidden"])
    assert {:ok, []} = Tracker.fetch_issues_by_states([])
    assert {:ok, []} = Tracker.fetch_issues_by_ids([])

    for {id, reason} <- [{"broken", "invalid_plane_page"}, {"repeated", "repeated_plane_cursor"}] do
      result = Tracker.execute_bound_agent_tool(binding, "plane_card", %{"action" => "comments"}, issue: %{card | id: id})
      refute result["success"]
      assert result["output"] =~ reason
    end

    assert :ok = stop_supervised(:plane_api)
    refute call.(%{"action" => "move", "value" => "Review"})["success"]
  end
end
