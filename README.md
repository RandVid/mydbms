# MyDBMS

> Solution for Homework 6* of the **Database Fundamentals** course.

A file-based DBMS built from scratch in Python 3.13. Stores data in typed binary pages on disk, supports SQL-like queries, and requires no external dependencies.

## Launch

```bash
python -m mydbms.dbms <directory>
```

The directory is created automatically on first run and holds all table data files plus a catalog.

**Example:**
```bash
python -m mydbms.dbms ./mydata
```

## Interactive session

```
MyDBMS (HW6*) — directory: ./mydata
Type SQL statements. Enter 'exit' or Ctrl-D to quit.

> CREATE TABLE users (id INT, name VARCHAR(50), age INT, active BOOL);
Table 'users' created
> INSERT INTO users VALUES (1, Alice, 30, TRUE);
Inserted 1 row
> INSERT INTO users VALUES (2, Bob, 25, FALSE);
Inserted 1 row
> SELECT * FROM users;
id | name  | age | active
---+-------+-----+-------
1  | Alice | 30  | True
2  | Bob   | 25  | False
(2 row(s))
> SELECT * FROM users WHERE active = TRUE;
(1 row(s))
> UPDATE users SET age = 31 WHERE name = Alice;
Updated 1 row(s)
> DELETE FROM users WHERE id = 2;
Deleted 1 row(s)
> exit
```

Data persists between sessions — reopen the same directory and your tables are still there.

## SQL reference

### CREATE TABLE
```sql
CREATE TABLE name (col1 TYPE, col2 TYPE, ...);
```

Supported types:

| Type | Description | Example |
|------|-------------|---------|
| `INT` | 64-bit signed integer | `42`, `-7` |
| `FLOAT` | 64-bit floating point | `3.14`, `-0.5` |
| `BOOL` | Boolean | `TRUE`, `FALSE` |
| `VARCHAR(n)` | Variable-length string, max `n` bytes | `VARCHAR(50)` |

### INSERT
```sql
INSERT INTO name VALUES (val1, val2, ...);
```

Values are positional and must match the column order. String values may optionally be quoted with single quotes.

### SELECT
```sql
SELECT * FROM name;
SELECT col1, col2 FROM name;
SELECT * FROM name WHERE col = value;
```

### UPDATE
```sql
UPDATE name SET col = value;
UPDATE name SET col = value WHERE other_col = val;
```

### DELETE
```sql
DELETE FROM name;
DELETE FROM name WHERE col = value;
```

### DROP TABLE
```sql
DROP TABLE name;
```

### WHERE clause

Supported operators: `=`, `!=`, `<`, `>`, `<=`, `>=`

```sql
SELECT * FROM products WHERE price > 100.0;
SELECT * FROM users WHERE active = TRUE;
SELECT * FROM orders WHERE status != shipped;
```
