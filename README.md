# Ksusha Rooms Engine (Python)

2D-движок на `pygame` с комнатами из JSON, разными покрытиями пола, объектами на карте и инвентарем.

## Что реализовано

- Карта подгружается из файла: `source/maps/main_map.json`.
- Комнаты задаются прямоугольниками с разными текстурами пола и размерами покрытия.
- На карте есть объекты:
  - `backpack` (подбор в инвентарь)
  - `sofa` (интеракция "touch" и переключение состояния)
  - `plant` (декор/препятствие)
  - `key` (маленькие ключи, подбор в инвентарь)
- Инвентарь на 5 слотов внизу экрана.
- Подбор рюкзака меняет спрайт персонажа на версию с рюкзаком.
- Выброс рюкзака возвращает спрайт персонажа без рюкзака.
- Подписи над объектами включаются параметром карты `world.show_object_labels`.

## Управление

- Стрелки: движение
- `E`: основной интеракт перед персонажем
  - подобрать объект (если у него есть `pickup_item_id`)
  - применить выбранный предмет к объекту (например нужный ключ к двери)
- `Q` / `W`: переключить активный слот инвентаря
- `R`:
  - если выбран предмет: использовать предмет на объекте перед персонажем
  - если предмет не выбран: "touch" объекта перед персонажем
  - для `sofa` touch циклически меняет спрайт дивана
- `G`: выбросить активный предмет впереди персонажа (включая ключи)
- `Space`: прыжок
- `F5`: hot reload карты и ассетов (без перезапуска приложения)
- `ESC`: выход

## Запуск

```bash
cd /Users/jekas/code/python/ксюша
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r python/requirements.txt
python python/ksusha_walk.py
```

Hot test mode (авто-перезагрузка):

```bash
KSU_DEV_HOT=1 python python/ksusha_walk.py
```

В этом режиме игра автоматически перезагружает `source/` при изменениях.

## Основные данные

- Карта: `source/maps/main_map.json`
- Персонаж без рюкзака: `source/textures/characters/ksu/walk/ksu.png`
- Персонаж с рюкзаком: `source/textures/characters/ksu/backpack/ksu_with_bag.png`
- Текстуры пола: `source/textures/floors/floor_tiles.png`
- Спрайты рюкзака: `source/textures/items/backpack/backpack_sheet.png`
- Спрайты диванов: `source/textures/items/sofa/sofa_sheet.png`
- Спрайты стен/дверей: `source/textures/walls/walls_sheet.png`

## Формат карты (кратко)

`source/maps/main_map.json`:

- `world`: размеры мира и точка спавна
  - `show_object_labels: true|false` — включить/выключить подписи над объектами
  - `player_stats` — характеристики персонажа:
    - `speed` — множитель скорости передвижения
    - `vision` — множитель радиусов видимости/фога
    - `jump_power` — множитель высоты прыжка
  - `fog` — настройки тумана (можно включать/выключать на карте):
    - `enabled: true|false` — включен ли фог
    - `near_radius` — ближняя квадратная зона (четко)
    - `mid_radius` — средняя квадратная зона (легкий blur + темнее)
    - `far_radius` — дальняя квадратная зона (сильный blur + еще темнее)
    - `dark_radius` — внешняя зона (почти темно)
    - `medium_blur_scale`, `far_blur_scale` — сила размытости
    - `mid_dark_alpha`, `far_dark_alpha`, `outer_dark_alpha` — затемнение по зонам
    - `transition` — плавность переходов между зонами (в пикселях)
    - `color: [r,g,b]` — цвет тумана/темноты
- `floors`: атлас пола, его сетка и словарь текстур
- `rooms`: зоны комнат (`x,y,width,height`) и `floor_texture`
  - для комнаты можно задать стены:
    - `walls_enabled: true|false`
    - `wall_thickness` — толщина стены
    - `top_door_width` — ширина верхнего проема
    - `top_door_offset` — смещение верхнего проема от центра
    - `left_opening_width`, `right_opening_width`, `bottom_opening_width` — ширина проемов слева/справа/снизу
    - `left_opening_offset`, `right_opening_offset`, `bottom_opening_offset` — смещение этих проемов
- `object_kinds`: поведение/слои/коллайдеры на уровне типа объекта (`backpack`, `sofa`)
- `objects`: экземпляры на карте и их `state` (с возможностью override свойств типа)
- добавлен тип объекта `plant` (вазоны)
- добавлен тип объекта `key` (ключи)
- для объектов можно задать:
  - `blocking: true|false` — непроходимый объект
  - `collider: [width, height]` — размер коллайдера (если нужен точный)
  - `cycle_sprites: true|false` — можно ли переключать спрайт объекта по `R` (touch)
  - `occlude_top: true|false` — верхняя часть объекта рисуется поверх персонажа
  - `occlude_split: 0..1` — граница разделения нижнего/верхнего слоя объекта
  - `jump_platform: [width, height, offset_y]` — зона приземления на верх объекта при прыжке
  - `label: "Text"` — подпись над объектом (рисуется только если включен `show_object_labels`)
  - `pickup_item_id: "item_id"` — предмет можно поднять в инвентарь
  - `required_item_id: "item_id"` — предмет, который нужен для применения к объекту
    - можно задавать разные ключи для разных дверей (например `key_blue`, `key_gold`)
  - `lock_key_sets: [[\"key_a\", \"key_b\"], [\"key_master\"]]` — массив замков:
    - каждый вложенный массив — ключи, которые подходят к конкретному замку
    - дверь откроется только когда открыты все замки
  - `lock_open_flags: [false, false]` — флаги состояния замков (опционально, если нужно предзадать)
  - `use_set_state: <int>` — в какое состояние перевести объект при успешном применении предмета
  - `use_set_blocking: true|false` — изменить проходимость объекта после применения
  - `consume_required_item: true|false` — удалить предмет из инвентаря после использования
