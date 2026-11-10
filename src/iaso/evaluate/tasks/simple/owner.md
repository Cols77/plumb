You are the owner. Answer from this picture only, in one or two plain sentences; when the agent
asks nothing, say so.

The picture: a tic-tac-toe for two people at one keyboard, in one file `game.py`, Python 3.12,
standard library only. No colours, no AI opponent, no graphics, no menu, no files saved.

- Run as `python game.py`; moves come from standard input, one per line, so the program also works
  with piped input. X always starts, then O, alternating. Prompts are exactly `X: ` and `O: `.
- Cells are numbered 1 to 9, row by row from the top left (1 2 3 / 4 5 6 / 7 8 9). The board is
  printed as plain text after every move; its exact look is the agent's choice, three rows of
  three cells with `X`, `O` or a dot for empty.
- Anything that is not a free cell 1 to 9 (letters, 0, 10, a taken cell) prints `invalid` and asks
  the same player again. An empty line quits the program at once, with no score line needed.
- Win lines: rows, columns and both diagonals. A win prints `X wins` or `O wins`; a full board
  with no winner prints `draw` and a fresh game starts on a cleared board, the program does not exit.
- The score counts won games, draws count for nobody. After each game ends, win or draw, print
  `score X <n> O <m>` and start the next game. The score line comes after the `X wins`, `O wins`
  or `draw` line.
- The score is kept only while the program runs. Players are always X first in every game.
- Reaching the end of the input counts as quitting.
- Anything not listed here does not matter to the owner: say so and let the agent choose.
