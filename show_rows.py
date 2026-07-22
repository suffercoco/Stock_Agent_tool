"""查看 stoch_data.db 中某个表的最后 N 行。

    uv run show_rows.py                # 默认显示最后 10 行
    uv run show_rows.py -n 25          # 显示最后 25 行
    uv run show_rows.py -n 5 -t readings   # 指定表名
"""

import argparse
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "stoch_data.db"

parser = argparse.ArgumentParser(description="查看表的最后 N 行")
parser.add_argument("-n", "--last", type=int, default=10,
                    help="显示最后几行（默认 10）")
parser.add_argument("-t", "--table", help="表名（默认取第一个表）")
args = parser.parse_args()

if not DB_PATH.exists():
    raise SystemExit(f"database not found: {DB_PATH}")

con = sqlite3.connect(DB_PATH)
cur = con.cursor()

# 先列出所有表名
cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [r[0] for r in cur.fetchall()]
print('数据库中的表:', tables)

table_name = args.table or tables[0]
if table_name not in tables:
    raise SystemExit(f'表 {table_name!r} 不存在')

# 打印列名，方便确认有没有 id / rowid 之类的排序依据
cur.execute(f"PRAGMA table_info({table_name});")
print('列信息:', cur.fetchall())

print(f'\n表 {table_name} 的最后{args.last}行:')

# 方法：用 SQLite 内置的 rowid 倒序取最后 N 条，再在 Python 里反转顺序，保持原始先后顺序展示
cur.execute(f"SELECT * FROM {table_name} ORDER BY rowid DESC LIMIT ?;", (args.last,))
rows = cur.fetchall()
rows.reverse()  # 反转回正常顺序（旧->新）

col_names = [desc[0] for desc in cur.description]
print(col_names)
for row in rows:
    print(row)

con.close()
