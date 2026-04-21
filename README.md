# Ksusha Rooms MVP

Проект содержит две части:
- Godot 4 MVP (`scenes/`, `scripts/`, `data/`)
- Python-версию игрового цикла на `pygame` (`python/`)

## Python: что пересобрано

Python-часть вынесена из монолитного скрипта в управляемую OOP-архитектуру:

- `python/ksusha_game/domain` - доменные сущности (игрок, направление)
- `python/ksusha_game/application` - игровой цикл и обработка ввода
- `python/ksusha_game/infrastructure` - загрузка/обработка спрайт-листа
- `python/ksusha_game/presentation` - отрисовка
- `python/ksusha_game/config.py` - централизованный конфиг
- `python/ksusha_walk.py` - совместимый entrypoint

Функциональность сохранена:
- управление `WASD`/стрелками
- анимация ходьбы из `source/textures/ksusha.png`
- масштаб персонажа от размера окна
- тень и ограничение движения границами окна

## Запуск Python-версии

```bash
python3 -m pip install -r python/requirements.txt
python3 python/ksusha_walk.py
```

Также можно запускать как модуль:

```bash
PYTHONPATH=python python3 -m ksusha_game
```

## Запуск Godot-версии

1. Открыть проект в Godot 4.
2. Нажать `Play`.
3. Управление: `WASD` или стрелки.

## Конфиг карты для Godot

Файл: `data/map_config.json`

- `grid_size`: размер сетки генерации
- `min_rooms`, `max_rooms`: диапазон комнат
- `seed`: `0` = случайный сид, число = фиксированный
- `room_types`: типы комнат и их `layouts`
