from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
import asyncio
import random

import os
bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()

SIZE = 8                      # размер поля
FLEET = [4, 3, 3, 2, 2, 1, 1]  # длины кораблей
ALL_CELLS = [(r, c) for r in range(SIZE) for c in range(SIZE)]

games = {}   # здесь хранятся игры всех игроков


# ---------- вспомогательные функции ----------

def around(cell):
    """Клетка и все 8 соседних (в пределах поля)."""
    r, c = cell
    result = []
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            nr, nc = r + dr, c + dc
            if 0 <= nr < SIZE and 0 <= nc < SIZE:
                result.append((nr, nc))
    return result


def place_fleet():
    """Случайно расставляет корабли так, чтобы они не касались друг друга."""
    while True:
        ships = []
        blocked = set()
        success = True
        for length in FLEET:
            placed = False
            for _ in range(200):
                if random.choice([True, False]):
                    r = random.randrange(SIZE)
                    c = random.randrange(SIZE - length + 1)
                    cells = [(r, c + i) for i in range(length)]
                else:
                    r = random.randrange(SIZE - length + 1)
                    c = random.randrange(SIZE)
                    cells = [(r + i, c) for i in range(length)]
                if not any(cell in blocked for cell in cells):
                    ships.append(set(cells))
                    for cell in cells:
                        blocked.update(around(cell))
                    placed = True
                    break
            if not placed:
                success = False
                break
        if success:
            return ships


def new_game():
    return {
        "enemy_ships": place_fleet(),   # корабли бота
        "my_ships": place_fleet(),      # твои корабли
        "my_shots": {},                 # твои выстрелы по боту
        "bot_shots": {},                # выстрелы бота по тебе
        "count": 0,
    }


def is_sunk(ship, shots):
    return all(shots.get(c) == "hit" for c in ship)


def count_sunk(ships, shots):
    return sum(1 for s in ships if is_sunk(s, shots))


def all_sunk(ships, shots):
    return count_sunk(ships, shots) == len(ships)


def fire(ships, shots, cell):
    """Выстрел. Возвращает 'miss', 'hit' или 'sunk'."""
    for ship in ships:
        if cell in ship:
            shots[cell] = "hit"
            if is_sunk(ship, shots):
                # вокруг потопленного корабля сразу отмечаем воду
                for c in ship:
                    for n in around(c):
                        if n not in shots:
                            shots[n] = "miss"
                return "sunk"
            return "hit"
    shots[cell] = "miss"
    return "miss"


def bot_choose(game):
    """Выбор клетки для выстрела бота: сначала добивает, иначе наугад."""
    shots = game["bot_shots"]

    sunk_cells = set()
    for ship in game["my_ships"]:
        if is_sunk(ship, shots):
            sunk_cells |= ship

    # попадания, где корабль ещё не потоплен
    active = [c for c, v in shots.items() if v == "hit" and c not in sunk_cells]

    candidates = []
    if len(active) == 1:
        r, c = active[0]
        candidates = [(r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)]
    elif len(active) >= 2:
        rows = {r for r, c in active}
        if len(rows) == 1:   # корабль лежит горизонтально
            r = active[0][0]
            cols = [c for _, c in active]
            candidates = [(r, min(cols) - 1), (r, max(cols) + 1)]
        else:                # вертикально
            c = active[0][1]
            rs = [r for r, _ in active]
            candidates = [(min(rs) - 1, c), (max(rs) + 1, c)]

    candidates = [
        x for x in candidates
        if 0 <= x[0] < SIZE and 0 <= x[1] < SIZE and x not in shots
    ]
    if candidates:
        return random.choice(candidates)

    free = [x for x in ALL_CELLS if x not in shots]
    return random.choice(free)


# ---------- отрисовка ----------

def make_keyboard(game, reveal=False):
    """Поле бота: по нему ты стреляешь."""
    kb = InlineKeyboardBuilder()
    for cell in ALL_CELLS:
        shot = game["my_shots"].get(cell)
        if shot == "hit":
            text = "💥"
        elif shot == "miss":
            text = "🌊"
        elif reveal and any(cell in s for s in game["enemy_ships"]):
            text = "🚢"
        else:
            text = "⬜"
        kb.button(text=text, callback_data=f"shot:{cell[0]}:{cell[1]}")
    kb.adjust(SIZE)
    return kb.as_markup()


def board_text(game):
    """Твоё поле в виде текста."""
    my_cells = set()
    for s in game["my_ships"]:
        my_cells |= s
    lines = []
    for r in range(SIZE):
        line = ""
        for c in range(SIZE):
            cell = (r, c)
            shot = game["bot_shots"].get(cell)
            if shot == "hit":
                line += "💥"
            elif shot == "miss":
                line += "🌊"
            elif cell in my_cells:
                line += "🚢"
            else:
                line += "🟦"
        lines.append(line)
    return "\n".join(lines)


def build_text(game, log):
    total = len(FLEET)
    a = count_sunk(game["enemy_ships"], game["my_shots"])
    b = count_sunk(game["my_ships"], game["bot_shots"])
    return (
        "\n".join(log)
        + f"\n\nТвоё поле:\n{board_text(game)}\n\n"
        + f"Потоплено кораблей у бота: {a} из {total}\n"
        + f"Потоплено у тебя: {b} из {total}"
    )


# ---------- обработчики ----------

# 1. Приветствие
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("Привет! Чем могу помочь?")


# 2. Запуск игры по слову "морской"
@dp.message(F.text.lower().contains("морской"))
async def start_game(message: types.Message):
    game = new_game()
    games[message.from_user.id] = game
    log = [
        "Играем! У каждого 7 кораблей: на 4, 3, 3, 2, 2, 1 и 1 клетку.",
        "Корабли не касаются друг друга. Попал или потопил, ходишь ещё раз.",
        "Стреляй по полю бота кнопками ниже.",
    ]
    await message.answer(build_text(game, log), reply_markup=make_keyboard(game))


# 3. Выстрелы по кнопкам
@dp.callback_query(F.data.startswith("shot:"))
async def shoot(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    game = games.get(user_id)
    if game is None:
        await callback.answer("Напиши «морской бой», чтобы начать игру")
        return

    _, r, c = callback.data.split(":")
    cell = (int(r), int(c))

    if cell in game["my_shots"]:
        await callback.answer("Сюда уже стреляли")
        return

    game["count"] += 1
    log = []

    # --- твой ход ---
    res = fire(game["enemy_ships"], game["my_shots"], cell)

    if all_sunk(game["enemy_ships"], game["my_shots"]):
        log.append(f"Победа! 🎉 Ты потопил все корабли бота за {game['count']} выстрелов.")
        log.append("Ещё раз? Напиши «морской бой»")
        text = build_text(game, log)
        del games[user_id]
        await callback.message.edit_text(text, reply_markup=make_keyboard(game, reveal=True))
        await callback.answer()
        return

    if res == "hit":
        log.append("Ты попал! 💥 Ходи ещё раз.")
        await callback.message.edit_text(build_text(game, log), reply_markup=make_keyboard(game))
        await callback.answer()
        return

    if res == "sunk":
        log.append("Ты потопил корабль! 🔥 Ходи ещё раз.")
        await callback.message.edit_text(build_text(game, log), reply_markup=make_keyboard(game))
        await callback.answer()
        return

    log.append("Ты промахнулся 🌊")

    # --- ходы бота (пока попадает, ходит дальше) ---
    while True:
        bot_cell = bot_choose(game)
        bres = fire(game["my_ships"], game["bot_shots"], bot_cell)

        if all_sunk(game["my_ships"], game["bot_shots"]):
            log.append("Бот потопил твой последний корабль. Проигрыш 😢")
            log.append("Реванш? Напиши «морской бой»")
            text = build_text(game, log)
            del games[user_id]
            await callback.message.edit_text(text, reply_markup=make_keyboard(game, reveal=True))
            await callback.answer()
            return

        if bres == "miss":
            log.append("Бот промахнулся 🌊 Твой ход.")
            break
        elif bres == "hit":
            log.append("Бот попал по твоему кораблю 💥")
        else:
            log.append("Бот потопил твой корабль 🔥")

    await callback.message.edit_text(build_text(game, log), reply_markup=make_keyboard(game))
    await callback.answer()


# 4. Повторялка для всего остального (должна быть последней!)
@dp.message()
async def echo(message: types.Message):
    await message.answer(f"Ты написал: {message.text}")


async def main():
    await dp.start_polling(bot)


asyncio.run(main())