# Материалы и небо

Скрипты собирают WAD, небо и фото. Часть входных изображений в репозиторий не входит.

## Скрипты

| Файл | Что делает |
|---|---|
| `generate.py` | создаёт 18 текстур `SN_*`, WAD `dist/cstrike/yz_seno_wheat.wad`, превью и контактные листы |
| `verify.py` | проверяет WAD, швы куба, солнце, размеры текстур |
| `build_giant_density.py` | из `reference_giant.jpg` делает `giant_density.npy` и `giant_shape.npy` |
| `build_sky_giant_clouds.py` | собирает шесть граней `yz_senowheat*.tga` из панорамы и плотности гиганта |
| `build_sky_panorama.py` | ранний вариант неба без гиганта, оставлен для сравнения |
| `build_photos.py` | добавляет в WAD 21 фото и табличку `YZ_CREDITS` |

## Каких файлов нет в репозитории

Положи их рядом с этим README:

- `sky_panorama_imagegen.png` — панорама-пейзаж 2:1, основа неба;
- `reference_giant.jpg` — изображение с гигантом для силуэта в облаках;
- папка с 21 фото (по умолчанию `assets/photos`, имена `f1`…`f21`).

## Порядок запуска

```powershell
py generate.py                  # WAD с 18 текстурами
py build_giant_density.py       # плотность и контур гиганта
py build_sky_giant_clouds.py    # шесть граней неба
py build_photos.py ..\photos    # 21 фото и табличка (после generate.py!)
py verify.py                    # проверки
```

`build_photos.py` **дописывает** WAD, поэтому запускать его нужно после `generate.py`. Повторный запуск `generate.py` перезапишет WAD без фото.
