class DBError(Exception):
    pass


class ParseError(DBError):
    pass


class TableExistsError(DBError):
    pass


class TableNotFoundError(DBError):
    pass


class ColumnNotFoundError(DBError):
    pass


class TypeMismatchError(DBError):
    pass


class StorageError(DBError):
    pass
