# yandex_zalupa — исходники

Исходники карты и плагина для Counter-Strike 1.6. Готовые файлы для установки лежат в отдельном репозитории `yandex_zalupa`.

## Что здесь есть

```
map/
  yandex_zalupa.map        редактируемая карта Valve 220
  generate_map.cjs         генератор карты (Node.js), из него получается .map
plugins/
  yz_seno_pyramid.sma      исходник плагина AMX Mod X
docs/
  PLUGIN.md                полное описание плагина
  MAP.md                   устройство карты, этапы, координаты
  BUILD.md                 как собрать карту, текстуры, небо и плагин
  CONTRACT.md              контракт между картой и плагином
assets/yz_seno_wheat.wad   готовый WAD: 18 текстур карты, 21 фото-текстура и табличка
assets/wheat_field/        скрипты текстур, неба и фото
models_src/                исходники моделей тюка и иголки
tools/build_full.ps1       сборка BSP с полным VIS
```

## Чего здесь нет

По решению автора в репозиторий не входят:

- исходные мем-фотографии (`assets/photos/`). При этом готовый `assets/yz_seno_wheat.wad` уже содержит их как текстуры `YZ_PHOTO_*`;
- референс гиганта для неба (`assets/wheat_field/reference_giant.jpg`);
- сторонний `studiomdl.exe` для сборки моделей.

Как их подставить, написано в `docs/BUILD.md` и в README соответствующих папок. Без них карта и плагин собираются, но небо с гигантом и фотографии на стенах не воспроизведутся.

## Быстрый старт

1. Скомпилировать плагин:

```
amxxpc.exe plugins/yz_seno_pyramid.sma -i<путь к include> -o yz_seno_pyramid.amxx -C+
```

2. Собрать карту:

```
tools/build_full.ps1 -Map map/yandex_zalupa.map -Out build/control
```

Полный VIS занимает около 25 минут — это нормально, подробности в `docs/BUILD.md`.

3. Собрать текстуры и небо:

```
cd assets/wheat_field
py generate.py
py build_giant_density.py
py build_sky_giant_clouds.py
```

## Документация

- `docs/PLUGIN.md` — как устроен плагин: cvar'ы, сущности, видимость, урон, этапы, финал, звуки, сборка, тесты.
- `docs/MAP.md` — этапы, комнаты, координаты, размещение фото.
- `docs/BUILD.md` — пошаговая сборка и требования к инструментам.

## Авторы

- **okay_google** — автор карты, плагина и материалов.
- **Claude (DeepSeek V4.1 Flash)** — соавтор: генератор карты, код плагина, документация, сборка и проверки.

Подробнее — в `CONTRIBUTORS.md`.

## Лицензия

MIT, см. `LICENSE`.
