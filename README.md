<a href="https://www.buymeacoffee.com/latealways" target="_blank"><img src="https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png" alt="Buy Me A Coffee" style="height: 41px !important;width: 174px !important;box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;-webkit-box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;" ></a>

# MHI2-to-MHS2 Map Converter
MHS2 units have reached end-of-life and are no longer receiving navigation map updates from Audi. However, MHI2 (Harman) units continue to receive new map data, and their map format is largely compatible with MHS2 after some structural changes.

This converter automates the process — it takes an MHI2 map archive and restructures it into the MHS2 directory layout, handling region data, speech resources, truffles, eggnog databases, and path remapping.

The one thing the converter cannot do is generate valid `content.sig` signature files. MHS2 validates map data against these signatures at load time, and since the file structure has changed, the original signatures are no longer valid. To work around this, a patched `libPresentationController.so` is required to bypass signature validation.

# Usage
1. Place your MHI2 map archive contents into the `Input` folder (Create the folder if it doesn't exist)
2. Run `python main.py` (no external dependencies required)
3. The converted MHS2 map will appear in the `Output` folder

The converter auto-detects the map region from the input data and uses multithreaded I/O, so conversion typically takes around 10–20 seconds.
