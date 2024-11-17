# MHI2-to-MHS2
Utility program that converts maps made specifically from the MHI2 Units in VAG Vehicles to maps that are valid for MHS2 Units from VAG Vehicles (mostly seen in Audi)

## NOT FINISHED
This converter converts about 89% of the map file. So, it will never actually work in a car unless you have the 100% AND the files must be valid (which right now, about 99.1% of the 89% are). The parts that are missing should be indicated in the code with a `TODO:` comment

## How to use
To use this, you need a map archive for MHI2 and you need to put it inside of a folder named `Input`. It should look like this

![{48E2A4BE-0ADF-46A4-88B1-FB03F24F8838}](https://github.com/user-attachments/assets/ac45b2ef-d5d3-4a02-ab49-daec5b1d40ea)

Then, run `python main.py` (No dependencies required) and let it do its job. It should take around 10 to 20 seconds. You will then see the MHS2 version in the `Output` folder.
