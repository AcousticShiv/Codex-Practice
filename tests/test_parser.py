from app.services.m_parser import parse_m_code


def test_detects_common_operations_in_order_and_step_names():
    m = """
let
  Source = Csv.Document("x"),
  Renamed = Table.RenameColumns(Source, {{"a", "b"}}),
  Typed = Table.TransformColumnTypes(Renamed, {{"b", type text}}),
  Filtered = Table.SelectRows(Typed, each [b] <> null)
in
  Filtered
"""
    steps = parse_m_code(m)
    assert [s.step_name for s in steps] == ["Renamed", "Typed", "Filtered"]
    assert [s.operation for s in steps] == ["Rename columns", "Change data types", "Filter rows"]


def test_handles_quoted_step_names():
    m = """
let
  Source = Csv.Document("x"),
  #"Removed Columns" = Table.RemoveColumns(Source,{"foo"})
in
  #"Removed Columns"
"""
    steps = parse_m_code(m)
    assert len(steps) == 1
    assert steps[0].step_name == "Removed Columns"
    assert steps[0].operation == "Remove columns"
