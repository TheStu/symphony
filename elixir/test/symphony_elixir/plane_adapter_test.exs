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

    assert issue.dispatchable
    assert issue.labels == ["reader"]
    assert {:ok, revised} = Adapter.issue(put_in(item, ["state", "name"], "Review"))
    assert revised.identifier == issue.identifier
    assert revised.state == "Review"
  end

  test "malformed responses cannot mark running cards missing" do
    assert {:error, :invalid_plane_item} = Adapter.issue(%{"id" => "abc"})
  end
end
