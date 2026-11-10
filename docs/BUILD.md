# Сборка

## Что нужно

- Node.js — для генератора карты.
- ZHLT v3.4 VL34 64-bit: `hlcsg_x64.exe`, `hlbsp_x64.exe`, `hlvis_x64.exe`, `hlrad_x64.exe`.
- AMX Mod X Compiler 1.9.0.5303: `amxxpc.exe` и папка `include`.
- Python 3.10 с `numpy` и `Pillow` — для текстур, неба и фото.
- J.A.C.K. — только если нужно править `.map` руками.

Пути к инструментам ниже — примеры, подставь свои.

## 1. Плагин

```powershell
amxxpc.exe plugins\yz_seno_pyramid.sma -i<путь>\include -o yz_seno_pyramid.amxx -C+
```

Флаг `-C+` включает компактное кодирование. Ожидаемый результат: 0 ошибок, 0 предупреждений, файл около 11.5 КБ.

## 2. Карта

Сначала перегенерировать `.map` из исходника:

```powershell
node map\generate_map.cjs
```

Затем собрать BSP в **новой** папке:

```powershell
$tools = "D:\SteamLibrary\steamapps\common\Half-Life\tools"
$out   = "build\control"
New-Item -ItemType Directory $out | Out-Null
Copy-Item map\yandex_zalupa.map "$out\control.map"

cd $out
& "$tools\hlcsg_x64.exe" -nowadtextures control.map
& "$tools\hlbsp_x64.exe" control.map
& "$tools\hlvis_x64.exe" control.map      # полный VIS, около 25 минут
& "$tools\hlrad_x64.exe" control.map
```

Или одной командой:

```powershell
tools\build_full.ps1 -Map map\yandex_zalupa.map -Out build\control
```

**Важно про VIS.** Быстрый режим `-fast` считается секунды, но отключает отсечение: клиент рисует 86% карты. Полный VIS занимает около 25 минут и снижает это до 31%. Скрипты с таймаутом 10 минут на стадию для этой карты не подходят.

Ожидаемые цифры полного VIS: 2360 листьев, 9476 порталов, в среднем видно 734 листа, данные видимости около 363 КБ.

## 3. Текстуры

```powershell
cd assets\wheat_field
py generate.py
py verify.py
```

`generate.py` создаёт `dist/cstrike/yz_seno_wheat.wad` с 18 текстурами `SN_*` и превью. Путь к WAD прописан в worldspawn карты; если меняешь структуру папок, поправь ключ `"wad"` в `map/generate_map.cjs`.

## 4. Небо с гигантом

В репозитории нет двух картинок, они не распространяются:

- `assets/wheat_field/sky_panorama_imagegen.png` — пейзаж-панорама 2:1;
- `assets/wheat_field/reference_giant.jpg` — картинка с гигантом.

Положи их на место и выполни:

```powershell
cd assets\wheat_field
py build_giant_density.py     # делает giant_density.npy и giant_shape.npy
py build_sky_giant_clouds.py  # собирает шесть граней yz_senowheat*.tga
```

Результат: `dist/cstrike/gfx/env/yz_senowheat{rt,lf,ft,bk,up,dn}.tga`, 256×256, 24 бита. Проверка швов и солнца — `py verify.py`.

## 5. Фотографии

В репозитории нет мем-фото. Положи 21 файл с именами `f1`…`f21` в `assets/photos/` (или передай папку аргументом) и выполни:

```powershell
cd assets\wheat_field
py build_photos.py ..\photos
```

Скрипт добавляет в WAD текстуры `YZ_PHOTO_01..21` и табличку `YZ_CREDITS`. Запускать **после** `generate.py`, иначе WAD будет перезаписан без фото. Каждое фото вписывается в 256×256 с тёмными полями, палитра — 256 цветов.

## 6. Установочный пакет

Структура для сервера:

```
cstrike/maps/yandex_zalupa.bsp
cstrike/yz_seno_wheat.wad
cstrike/gfx/env/yz_senowheat*.tga
cstrike/models/yz_seno/bale.mdl
cstrike/models/yz_seno/needle.mdl
cstrike/sound/yz_seno/bale_break.wav
cstrike/addons/amxmodx/plugins/yz_seno_pyramid.amxx
```

## 7. Порядок, если меняешь геометрию

1. Правка `generate_map.cjs` → `node map\generate_map.cjs`.
2. Полная пересборка BSP, включая VIS.
3. Если менял только текстуры, но не геометрию, VIS можно не пересчитывать: сравни `.prt` со старой сборкой. Если файлы совпадают, данные видимости переносятся. На практике панели `func_detail` тоже сдвигают порталы, поэтому после добавления фото VIS считался заново.
