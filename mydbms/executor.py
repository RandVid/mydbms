from __future__ import annotations
from sql.parser import (
    CreateTableStmt, InsertStmt, SelectStmt, UpdateStmt, DeleteStmt,
    DropTableStmt, WhereClause, ColumnDef as ParserColDef,
)
from sql.errors import ColumnNotFoundError, TypeMismatchError
from mydbms.catalog import TypedCatalog
from mydbms.heap_file import PagedHeapFile
from mydbms.types import ColumnDef, DataType, coerce


_TYPE_MAP = {
    "INT": DataType.INT,
    "INTEGER": DataType.INT,
    "FLOAT": DataType.FLOAT,
    "REAL": DataType.FLOAT,
    "BOOL": DataType.BOOL,
    "BOOLEAN": DataType.BOOL,
    "VARCHAR": DataType.VARCHAR,
    "CHAR": DataType.VARCHAR,
    "STRING": DataType.VARCHAR,
    "TEXT": DataType.VARCHAR,
}


def _parser_col_to_typed(p: ParserColDef, index: int) -> ColumnDef:
    dtype = _TYPE_MAP.get(p.type_str.upper(), DataType.VARCHAR)
    return ColumnDef(
        name=p.name,
        dtype=dtype,
        varchar_max=p.width if p.width else 255,
        index=index,
    )


def _eval_where(row: dict, where: WhereClause, schema: list[ColumnDef]) -> bool:
    col_def = next((c for c in schema if c.name == where.column), None)
    if col_def is None:
        raise ColumnNotFoundError(f"Column '{where.column}' not found")
    cell = row.get(where.column)
    try:
        val = coerce(where.value, col_def)
    except TypeMismatchError:
        val = where.value  # fallback: string comparison

    if cell is None or val is None:
        return False

    match where.op:
        case "=":  return cell == val
        case "!=": return cell != val
        case "<":  return cell < val
        case ">":  return cell > val
        case "<=": return cell <= val
        case ">=": return cell >= val
    return False


def execute(stmt, catalog: TypedCatalog, heap: PagedHeapFile):
    if isinstance(stmt, CreateTableStmt):
        cols = [_parser_col_to_typed(c, i) for i, c in enumerate(stmt.columns)]
        catalog.create_table(stmt.table_name, cols)
        return f"Table '{stmt.table_name}' created"

    if isinstance(stmt, InsertStmt):
        schema = catalog.get_schema(stmt.table_name)
        if len(stmt.values) != len(schema):
            raise ValueError(
                f"Expected {len(schema)} values, got {len(stmt.values)}"
            )
        row = {c.name: coerce(v, c) for c, v in zip(schema, stmt.values)}
        heap.insert(stmt.table_name, row, schema)
        return "Inserted 1 row"

    if isinstance(stmt, SelectStmt):
        schema = catalog.get_schema(stmt.table_name)
        rows = []
        for _, row in heap.scan(stmt.table_name, schema):
            if stmt.where and not _eval_where(row, stmt.where, schema):
                continue
            if stmt.columns == ["*"]:
                rows.append(row)
            else:
                rows.append({c: row.get(c) for c in stmt.columns})
        return rows

    if isinstance(stmt, UpdateStmt):
        schema = catalog.get_schema(stmt.table_name)
        col_map = {c.name: c for c in schema}
        updated = 0
        for rid, row in list(heap.scan(stmt.table_name, schema)):
            if stmt.where and not _eval_where(row, stmt.where, schema):
                continue
            new_row = dict(row)
            for col_name, raw_val in stmt.assignments.items():
                if col_name not in col_map:
                    raise ColumnNotFoundError(f"Column '{col_name}' not found")
                new_row[col_name] = coerce(raw_val, col_map[col_name])
            heap.update(stmt.table_name, rid, new_row, schema)
            updated += 1
        return f"Updated {updated} row(s)"

    if isinstance(stmt, DeleteStmt):
        schema = catalog.get_schema(stmt.table_name)
        deleted = 0
        for rid, row in list(heap.scan(stmt.table_name, schema)):
            if stmt.where and not _eval_where(row, stmt.where, schema):
                continue
            heap.delete(stmt.table_name, rid)
            deleted += 1
        return f"Deleted {deleted} row(s)"

    if isinstance(stmt, DropTableStmt):
        catalog.drop_table(stmt.table_name)
        return f"Table '{stmt.table_name}' dropped"

    raise NotImplementedError(f"Unknown statement type: {type(stmt)}")
