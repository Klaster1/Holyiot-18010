# Fonts

Open-licensed fonts used by the ShapeString objects in `Holyiot.FCStd`. They are bundled so the document renders the same on any machine. The objects reference these files with paths like `./fonts/...`, relative to the `.FCStd`.

| File | Used for | Licence |
| --- | --- | --- |
| `RobotoCondensed-Bold.ttf` | Pin labels | SIL OFL 1.1 |
| `RobotoCondensed-Regular.ttf` | PCB silkscreen | SIL OFL 1.1 |
| `Roboto-Regular.ttf` | Laser marking on the shield can | SIL OFL 1.1 |
| `Quicksand-Light.ttf` | "holyiot" logo on the shield can | SIL OFL 1.1 |

The files are the Latin subsets from [Fontsource](https://fontsource.org). Copyright: The Roboto Project Authors and The Quicksand Project Authors. The full licence text is in `OFL.txt`.

Overlapping contours were merged with fontTools (`removeOverlaps`), because FreeCAD's ShapeString draws overlapping contours incorrectly. The OFL permits modified versions; none of these fonts declare a Reserved Font Name.
