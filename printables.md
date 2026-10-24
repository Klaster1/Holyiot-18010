# Printables listing

Fields for the Printables upload form.

## Title

Holyiot-18010 (nRF52840) module - STEP model

## Summary

STEP model of the Holyiot-18010 nRF52840 BLE module with accurate pad positions, for designing programming and test jigs.

## File

`export/Holyiot-18010.step`

## Category

TODO

## Tags

nrf52840, holyiot, ble, bluetooth, step, jig, pogo-pin, castellated, pcb, module

## License

Public Domain (CC0 1.0)

## Description

STEP model of the [Holyiot-18010](http://www.holyiot.com/tp/2019042516322180424.pdf) nRF52840 BLE module, for designing programming and test jigs. The parametric FreeCAD source, the pinout spreadsheet, labelled pads and renders are on GitHub: [Klaster1/Holyiot-18010](https://github.com/Klaster1/Holyiot-18010).

The STEP is an assembly of named, coloured parts: PCB, castellated pads 1-37, inner pads 38-55, shield can, chip antenna and its end caps.

Accuracy:

- Pad positions, the 1.1 mm pitch and the outline come from the datasheet's mechanical drawing.
- Pad sizes, the shield can and the antenna are measured from the product photos.
- Three heights are estimates: the datasheet omits them, and the vendor gives 2.7 mm in total. Measure your module before you print a jig. In the model, the PCB is 1.0 mm thick, the shield can is 1.7 mm high and the antenna is 1.0 mm high.

Coordinates: the origin is the board centre, the PCB bottom face is at z = 0, and +Y points towards the antenna. Pin 1 is top-left when you look down on the shield.

Pins for programming over SWD or USB:

| Pin | Name | Use |
| --- | --- | --- |
| 14 | VDD_nRF | Supply, 3.9 V max |
| 1, 25, 37 | GND | Ground |
| 31 | SWDCLK | SWD clock |
| 32 | SWDIO | SWD data |
| 21 | P0.18 | nRESET |
| 22, 23, 24 | VBUS, D-, D+ | USB, 5.8 V max on VBUS |

The positions of all 55 pads are in the `Pinout` spreadsheet of the FreeCAD model on GitHub.
