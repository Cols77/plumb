You are the owner. Answer from this picture only, in one or two plain sentences; when the agent
asks nothing, say so.

The picture: a command-line expense tracker in one file `expenses.py`, Python 3.12, standard
library only, no colours, no database, no packages. Data lives in CSV files beside the script
(the folder `expenses.py` is in).

- `python expenses.py add <YYYY-MM-DD> <category> <amount> [note]`: appends a row to
  `expenses.csv`, columns `date,category,amount,note` (a header line is fine). The note is
  optional and may contain spaces when the shell passes it as one argument. Categories are one
  lower-case word, kept as typed.
- `python expenses.py list`: one line per expense in the order they were added: date, category,
  amount, note, separated by single spaces.
- `python expenses.py report <YYYY-MM>`: for that month, one line `<category> <total>` per
  category, sorted by category name, then `total <sum>`. A month with nothing prints `total 0`.
- `python expenses.py budget <category> <amount>`: sets that category's monthly budget in
  `budgets.csv` (columns `category,amount`); setting it again replaces it. `add` prints
  `over budget: <category>` when the month's total for that category (including the new expense)
  is strictly more than the budget; the expense is still stored.
- Request 1 first said amounts are decimal like 12.50; request 4 changes that to whole cents for
  good: `add` and `budget` take an integer number of cents (1250, never 12.50), every amount is
  printed as cents (1250), and a decimal amount prints `invalid amount` and stores nothing.
  Rows already stored as decimals are converted once to cents (12.50 becomes 1250).
- `python expenses.py import <file.csv>`: header `Description,Amount,Date`, date DD/MM/YYYY,
  amount in cents, negative for spending. Each spending row is added as an expense of category
  `bank`, the description as its note, the date converted to YYYY-MM-DD, the amount stored as a
  positive number of cents. Positive rows (income) are skipped. It does not trigger budget
  warnings.
- Errors (unknown command, bad date) print a one-line message and exit with a non-zero code.
- Anything not listed here does not matter to the owner: say so and let the agent choose.
