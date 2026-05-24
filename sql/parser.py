from __future__ import annotations
import re
from dataclasses import dataclass, field
from sql.errors import ParseError


# ---------------------------------------------------------------------------
# AST nodes
# ---------------------------------------------------------------------------

@dataclass
class ColumnDef:
    name: str
    type_str: str   # raw type token, e.g. 'VARCHAR(30)', 'INT', 'BOOL'
    width: int = 0  # extracted n from VARCHAR(n); 0 for fixed-size types


@dataclass
class WhereClause:
    column: str
    op: str         # '=', '<', '>', '<=', '>=', '!='
    value: str      # raw string token (quotes already stripped)


@dataclass
class CreateTableStmt:
    table_name: str
    columns: list[ColumnDef]


@dataclass
class InsertStmt:
    table_name: str
    values: list[str]


@dataclass
class SelectStmt:
    table_name: str
    columns: list[str]          # ['*'] or named list
    where: WhereClause | None = None


@dataclass
class UpdateStmt:
    table_name: str
    assignments: dict[str, str]
    where: WhereClause | None = None


@dataclass
class DeleteStmt:
    table_name: str
    where: WhereClause | None = None


@dataclass
class DropTableStmt:
    table_name: str


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"'[^']*'"          # single-quoted string
    r"|!=|<=|>="        # two-char operators
    r"|[=<>]"           # single-char operators
    r"|[(),;*]"         # punctuation
    r"|[A-Za-z_]\w*"   # identifier / keyword
    r"|[-+]?\d+(?:\.\d+)?"  # number (int or float)
    r"|\"[^\"]*\""      # double-quoted string
)

_KEYWORDS = {
    "CREATE", "TABLE", "INSERT", "INTO", "VALUES",
    "SELECT", "FROM", "WHERE", "UPDATE", "SET",
    "DELETE", "DROP", "AND", "OR", "NOT",
    "TRUE", "FALSE", "NULL",
}


def _tokenize(sql: str) -> list[str]:
    tokens = _TOKEN_RE.findall(sql.strip().rstrip(";"))
    return tokens


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class Parser:
    def __init__(self, sql: str):
        self._tokens = _tokenize(sql)
        self._pos = 0

    # -- helpers --

    def _peek(self) -> str | None:
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return None

    def _consume(self) -> str:
        tok = self._peek()
        if tok is None:
            raise ParseError("Unexpected end of input")
        self._pos += 1
        return tok

    def _expect(self, value: str) -> str:
        tok = self._consume()
        if tok.upper() != value.upper():
            raise ParseError(f"Expected '{value}', got '{tok}'")
        return tok

    def _expect_ident(self) -> str:
        tok = self._consume()
        if not tok or tok.upper() in _KEYWORDS or tok[0] in "'\"(),;*=<>!":
            raise ParseError(f"Expected identifier, got '{tok}'")
        return tok

    def _match(self, value: str) -> bool:
        if self._peek() and self._peek().upper() == value.upper():
            self._pos += 1
            return True
        return False

    def _strip_quotes(self, tok: str) -> str:
        if (tok.startswith("'") and tok.endswith("'")) or \
           (tok.startswith('"') and tok.endswith('"')):
            return tok[1:-1]
        return tok

    # -- type parsing --

    def _parse_type(self) -> ColumnDef:
        """Parse a column definition 'name TYPE' and return ColumnDef."""
        name = self._expect_ident()
        type_tok = self._peek()
        if type_tok is None or type_tok in (",", ")"):
            # no type given — treat as string with no declared width
            return ColumnDef(name=name, type_str="VARCHAR", width=255)

        type_upper = type_tok.upper()
        if type_upper in ("INT", "INTEGER", "FLOAT", "REAL", "BOOL", "BOOLEAN", "DATE"):
            self._consume()
            return ColumnDef(name=name, type_str=type_upper, width=0)

        if type_upper in ("VARCHAR", "CHAR", "STRING", "TEXT"):
            self._consume()
            width = 255
            if self._peek() == "(":
                self._consume()  # (
                n_tok = self._consume()
                try:
                    width = int(n_tok)
                except ValueError:
                    raise ParseError(f"Expected integer width, got '{n_tok}'")
                self._expect(")")
            return ColumnDef(name=name, type_str="VARCHAR", width=width)

        raise ParseError(f"Unknown type: '{type_tok}'")

    # -- WHERE --

    def _parse_where(self) -> WhereClause:
        col = self._expect_ident()
        op_tok = self._consume()
        if op_tok not in ("=", "<", ">", "<=", ">=", "!="):
            raise ParseError(f"Expected comparison operator, got '{op_tok}'")
        val_tok = self._consume()
        return WhereClause(column=col, op=op_tok, value=self._strip_quotes(val_tok))

    # -- statement parsers --

    def _parse_create_table(self) -> CreateTableStmt:
        self._expect("TABLE")
        name = self._expect_ident()
        self._expect("(")
        cols: list[ColumnDef] = []
        while True:
            cols.append(self._parse_type())
            if self._peek() == ")":
                self._consume()
                break
            self._expect(",")
        if not cols:
            raise ParseError("CREATE TABLE requires at least one column")
        return CreateTableStmt(table_name=name, columns=cols)

    def _parse_insert(self) -> InsertStmt:
        self._expect("INTO")
        name = self._expect_ident()
        self._expect("VALUES")
        self._expect("(")
        values: list[str] = []
        while True:
            tok = self._consume()
            values.append(self._strip_quotes(tok))
            if self._peek() == ")":
                self._consume()
                break
            self._expect(",")
        return InsertStmt(table_name=name, values=values)

    def _parse_select(self) -> SelectStmt:
        cols: list[str] = []
        tok = self._peek()
        if tok == "*":
            self._consume()
            cols = ["*"]
        else:
            while True:
                cols.append(self._expect_ident())
                if self._peek() == ",":
                    self._consume()
                else:
                    break
        self._expect("FROM")
        name = self._expect_ident()
        where = None
        if self._match("WHERE"):
            where = self._parse_where()
        return SelectStmt(table_name=name, columns=cols, where=where)

    def _parse_update(self) -> UpdateStmt:
        name = self._expect_ident()
        self._expect("SET")
        assignments: dict[str, str] = {}
        while True:
            col = self._expect_ident()
            self._expect("=")
            val = self._strip_quotes(self._consume())
            assignments[col] = val
            if self._peek() == ",":
                self._consume()
            else:
                break
        where = None
        if self._match("WHERE"):
            where = self._parse_where()
        return UpdateStmt(table_name=name, assignments=assignments, where=where)

    def _parse_delete(self) -> DeleteStmt:
        self._expect("FROM")
        name = self._expect_ident()
        where = None
        if self._match("WHERE"):
            where = self._parse_where()
        return DeleteStmt(table_name=name, where=where)

    def _parse_drop(self) -> DropTableStmt:
        self._expect("TABLE")
        name = self._expect_ident()
        return DropTableStmt(table_name=name)

    # -- entry point --

    def parse(self):
        kw = self._consume().upper()
        if kw == "CREATE":
            return self._parse_create_table()
        if kw == "INSERT":
            return self._parse_insert()
        if kw == "SELECT":
            return self._parse_select()
        if kw == "UPDATE":
            return self._parse_update()
        if kw == "DELETE":
            return self._parse_delete()
        if kw == "DROP":
            return self._parse_drop()
        raise ParseError(f"Unknown statement keyword: '{kw}'")


def parse(sql: str):
    """Parse an SQL statement and return the corresponding AST node."""
    return Parser(sql).parse()
