defmodule SymphonyElixir.Plane.AdapterTest do
  use ExUnit.Case, async: true
  alias SymphonyElixir.Plane.Adapter

  test "a Plane card keeps a stable workspace and named board state on revision" do
    item = %{
      "id" => "abc",
      "sequence_id" => 23,
      "name" => "Adjust shelf",
      "state" => %{"name" => "Ready"},
      "priority" => "high",
      "description_html" => "<p>Use orange</p>",
      "labels" => [%{"name" => "reader"}]
    }

    assert {:ok, issue} = Adapter.issue(item)

    assert {issue.id, issue.identifier, issue.title, issue.priority} ==
             {"abc", "PL-23", "Adjust shelf", 2}

    assert {:ok, dated} = Adapter.issue(Map.merge(item, %{"created_at" => "2026-01-01T00:00:00Z", "updated_at" => "invalid"}))
    assert dated.created_at == ~U[2026-01-01 00:00:00Z]
    assert is_nil(dated.updated_at)
    assert issue.dispatchable
    assert issue.labels == ["reader"]
    assert {:ok, revised} = Adapter.issue(put_in(item, ["state", "name"], "Review"))
    assert revised.identifier == issue.identifier
    assert revised.state == "Review"
  end

  test "malformed responses cannot mark running cards missing" do
    assert {:error, :invalid_plane_item} = Adapter.issue(%{"id" => "abc"})
  end

  test "invalid scope and origin settings fail closed" do
    states = %{active_states: ["Ready"], terminal_states: ["Done"]}
    base = %{"url" => "https://example.com", "workspace" => "books", "project_id" => Ecto.UUID.generate()}
    assert {:error, :missing_plane_states} = Adapter.validate_config(%{})
    assert {:error, :missing_plane_settings} = Adapter.validate_config(states)

    for override <- [%{"url" => "http://remote.test"}, %{"url" => "https://user@example.com/?key=1"}, %{"workspace" => "../other"}, %{"project_id" => "not-a-uuid"}] do
      assert {:error, _} = Adapter.validate_config(Map.put(states, :provider, Map.merge(base, override)))
    end
  end
end
