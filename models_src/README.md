# Модели для seno_field

Исходники модели и процедурных текстур создаются командой `node generate.cjs`. Полная повторная сборка в PowerShell: `./build.ps1`. Нужны Node.js и компилятор `tools/studiomdl.exe`; скрипт сверяет его SHA-256 перед запуском и сохраняет журналы компиляции рядом с исходниками.

Компилятор: StudioMDL SC, 21.12.2020, снимок Sven Co-op SDK, файл взят из [публичного архива GoldSrc Model Toolchain](https://github.com/XiangXtreme/goldsrc-model-toolchain/blob/main/plugin/goldsrc_model_toolchain/bin/windows-x64/studiomdl.exe). Хеш `a96afa8b711be20e706fadcbe0f62d996812c4b3ccc3c4e3b617a3a12550276a` соответствует [манифесту](https://github.com/XiangXtreme/goldsrc-model-toolchain/blob/main/tool-manifest.json). Это стороннее распространение SDK, а не установленный у пользователя инструмент.

- `bale.mdl`: куб со стороной 48 единиц, 12 треугольников; `hay.bmp` встроена в модель.
- `needle.mdl`: иголка высотой 20 единиц, 52 треугольника; `needle.bmp` встроена в модель. Объём видимой геометрии находится внутри куба коллизии ±10 единиц.

Скопировать содержимое `models/seno_field/` в `cstrike/models/seno_field/` сервера; плагин указывает эти пути. WAD для двух моделей не требуется. Динамические объекты создаются плагином и не требуют размещения в J.A.C.K. По исходникам проверены размеры, версия MDL и наличие текстуры, а коллизию и видимость необходимо проверить в CS 1.6.
