import hashlib
import json
import os
import shutil
import time
from hashesparser import parse_hashes_file, HashesFile, generate_checksum

OUTPUT_DIR = "Output"
INPUT_DIR = "Input"

old_print = print
def print(*args, **kwargs):
    old_print(*args, **kwargs)
    with open("log.txt", "a") as f:
        old_print(*args, **kwargs, file=f)

def get_hash_of_file(path: str):
    g = hashlib.sha1()
    with open(path, 'rb') as f:
        l = f.read()
        g.update(l)
    return g.hexdigest()


def copy_file_to_output(input_path, output_path):
    if not os.path.isdir(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    # create missing directories in output_dir
    if "/" in output_path:
        os.makedirs(os.path.join(OUTPUT_DIR, *output_path.split("/")[:-1]), exist_ok=True)
    shutil.copy(os.path.join(INPUT_DIR, input_path), os.path.join(OUTPUT_DIR, output_path))


useful_vars = {
    "region": lambda: [directory for directory in next(os.walk(os.path.join(INPUT_DIR, "Mib1", "Eggnog")))[1] if
                       directory != "DBInfo" and directory != "InfoFile"][0],
    "REGION": lambda: get_var("region").upper(),
}


def get_var(name: str):
    if name in useful_vars:
        return useful_vars[name]()
    return None


conversion_paths = {
    "Mib2/NavDB/InfoFile/0/default/Update.txt": "database/Update.txt",
    "Mib1/Eggnog/{region}/0/default/EggnogDB.ser": "database/{region}/eggnog/eggnog_light/EggnogDB.ser",
    "Mib2/NavDB/common_{region}/0/default/CountryBorders_WorldCartographicLayer_Basic.psf": "database/{region}/map/common/CountryBorders_WorldCartographicLayer_Basic.psf",
    "Mib2/NavDB/common_{region}/0/default/DTM_{REGION}_Texture.psf": "database/{region}/map/common/DTM_{REGION}_Texture.psf",
    "Mib2/NavDB/common_{region}/0/default/Topomap_{REGION}_Texture.psf": "database/{region}/map/common/Topomap_{REGION}_Texture.psf",
    "Mib2/NavDB/common_{region}/0/default/Topomap_World_Texture.psf": "database/{region}/map/common/Topomap_World_Texture.psf",
    "Mib2/NavDB/common_{region}/0/default/WorldCartographicLayer_Basic.psf": "database/{region}/map/common/WorldCartographicLayer_Basic.psf",
    "Mib1/Eggnog/DBInfo/0/default/EggnogDBInfo.txt": "eggnog/EggnogDBInfo.txt",
    "Mib1/Eggnog/InfoFile/0/default/Update.txt": "eggnog/Update.txt",
    "Mib2/SpeechResVDE/InfoFile/0/default/Update.txt": "speech/sr/vde/Update.txt",
    "Mib2/NavDB/common_{region}/0/default/content.pkg": "database/{region}/map/common/content.pkg",
    "Mib2/NavDB/common_{region}/0/default/content.sig": "database/{region}/map/common/content.sig",
    "Mib2/NavDB/common_{region}/0/default/hashes.txt": "database/{region}/map/common/hashes.txt"
}
progress = 0


def run():
    global progress
    progress = 0

    total = sum([1 if isinstance(out, str) else len(out) for out in conversion_paths.values()])
    errors = []

    print("Region detected: " + get_var("REGION"))

    def do_file(input_path, output_path):
        try:
            copy_file_to_output(input_path, output_path)
            return True, None
        except Exception as e:
            return False, e

    def pre_do_file(input_path, output_path, count=False):
        global progress
        input_path = input_path.replace("\\", "/")
        output_path = output_path.replace("\\", "/")
        r, e = do_file(input_path, output_path)
        if r:
            if count:
                progress += 1
            print(
                f"Copying {input_path} to {output_path}.{f' Progress: {progress}/{total} ({int((progress / total) * 10000) / 100}%)' if count else ''}")
        else:
            if count:
                errors.append(input_path)
            print(f"Error copying {input_path} to {output_path}. Error: {e}")

    def replace_vars(string):
        for var in useful_vars:
            string = string.replace("{" + var + "}", get_var(var))
        return string

    start_time = time.time()
    print("Copying general files...")
    for input_path, output_path in conversion_paths.items():
        input_path = replace_vars(input_path)
        if isinstance(output_path, list):
            output_path = [replace_vars(out) for out in output_path]
            for path in output_path:
                pre_do_file(input_path, path, True)
            continue
        output_path = replace_vars(output_path)
        pre_do_file(input_path, output_path, True)

    print("Generating custom missing files...")

    regionList_JSON = open(
        os.path.join(INPUT_DIR, "Mib2", "NavDB", "RegionList_" + get_var("region"), "0", "default", "regionList.json"),
        "r").read().replace("/net/mmx/mnt/navdb/", "")
    with open(os.path.join(OUTPUT_DIR, "database", get_var("region"), "regionList.json"), "w") as f:
        f.write(regionList_JSON)
        f.close()

    content = open(os.path.join(INPUT_DIR, "Mib2", "NavDB", "DBInfo", "0", "default", "DBInfo.txt"), "r").readlines()
    newlines = []
    with open(os.path.join(OUTPUT_DIR, "DBInfo.txt"), "w") as f:
        for line in content:
            if line.startswith("PartNumber") and not line.startswith("PartNumber1="):
                continue
            elif line.startswith("PartNumber1="):
                line = "PartNumber1=\"V03959803PS\"\n"
            newlines.append(line)
        f.writelines(newlines)
        f.close()

    with open(os.path.join(OUTPUT_DIR, "database", get_var("region"), "eggnog", "eggnog_light", "hashes.txt"), "w") as f:
        f.write(str(HashesFile("EggnogDB.ser", None,
                               str(len(open(os.path.join(OUTPUT_DIR, "database", get_var("region"), "eggnog", "eggnog_light", "EggnogDB.ser"), "rb").read())),
                               generate_checksum(os.path.join(OUTPUT_DIR, "database", get_var("region"), "eggnog", "eggnog_light", "EggnogDB.ser")), "524288")))
        f.close()

    with open(os.path.join(OUTPUT_DIR, "database", "DBInfo.txt"), "w") as f:
        f.writelines(newlines)
        f.close()

    otaInfo_converted = open(os.path.join(INPUT_DIR, "Mib2", "SpeechResVDE", "otaInfo", "0", "default", "otaInfo.txt"),
                             "r").read().replace("/net/mmx/mnt/navdb/speech/sr/vde", ".")
    with open(OUTPUT_DIR + "/speech/sr/vde/otaInfo.txt", "w") as f:
        f.write(otaInfo_converted)
        f.close()

    regionList_converted = open(
        os.path.join(INPUT_DIR, "Mib2", "SpeechResVDE", "regionList", "0", "default", "regionList.txt"),
        "r").read().replace("/net/mmx/mnt/navdb/speech/sr/vde", ".")
    with open(OUTPUT_DIR + "/speech/sr/vde/regionList.txt", "w") as f:
        f.write(regionList_converted)
        f.close()

    print("Translating regions...")

    # Generate folders
    for region in json.loads(regionList_JSON)["regions"]:
        os.makedirs(os.path.join(OUTPUT_DIR, region["directory"]))

    folders_generated = os.listdir(os.path.join(OUTPUT_DIR, "database", get_var("region"), "map", "regions"))
    for folder in folders_generated:
        # Get hashes
        hashes = parse_hashes_file(
            os.path.join(INPUT_DIR, "Mib2", "NavDB", folder + "_" + get_var("region"), "0", "default", "hashes.txt"))
        hashes = {hash.Destination if hash.Destination is not None else hash.FileName: hash for hash in hashes}

        # Prepare output hashes.txt
        output_hashes = ""

        # Convert .psf files
        content_pkg = json.load(open(
            os.path.join(INPUT_DIR, "Mib2", "NavDB", folder + "_" + get_var("region"), "0", "default", "content.pkg")))
        for content_file in content_pkg["file"]:
            if hashes[content_file["name"]].Destination is not None:
                hashes[content_file["name"]].FileName = hashes[content_file["name"]].Destination
                hashes[content_file["name"]].Destination = None

            output_hashes += str(hashes[content_file["name"]])
            location = content_file["name"] if "source" not in content_file.keys() else os.path.join(
                content_file["source"], content_file["name"])
            if not content_file["name"].startswith("Models/"):
                pre_do_file(os.path.join("Mib2", "NavDB", folder + "_" + get_var("region"), "0", "default", location),
                            os.path.join("database", get_var("region"), "map", "regions", folder, content_file["name"]))

        # Write hashes.txt
        with open(os.path.join(OUTPUT_DIR, "database", get_var("region"), "map", "regions", folder, "hashes.txt"),
                  "w") as f:
            f.write(output_hashes)
            f.close()

    # TODO: content.pkg and content.sig

    print("Copying speech files...")

    # Speech files (speech/sr/vde)
    for folder in os.listdir(os.path.join(INPUT_DIR, "Mib2", "SpeechResVDE")):
        if folder.startswith(get_var("REGION") + "_"):
            for file in os.listdir(os.path.join(INPUT_DIR, "Mib2", "SpeechResVDE", folder, "0", "default")):
                pre_do_file(os.path.join("Mib2", "SpeechResVDE", folder, "0", "default", file),
                            os.path.join("speech", "sr", "vde", get_var("REGION"),
                                         folder[len(get_var("REGION") + "_"):], file))

    # eggnog/hashes.txt
    with open(os.path.join(OUTPUT_DIR, "eggnog", "hashes.txt"), "w") as f:
        f.write(str(HashesFile("EggnogDBInfo.txt", None,
                               str(len(open(os.path.join(OUTPUT_DIR, "eggnog", "EggnogDBInfo.txt"), "rb").read())),
                               [get_hash_of_file(os.path.join(OUTPUT_DIR, "eggnog", "EggnogDBInfo.txt"))], "524288")))
        f.write(str(HashesFile("Update.txt", None,
                               str(len(open(os.path.join(OUTPUT_DIR, "eggnog", "Update.txt"), "rb").read())),
                               [get_hash_of_file(os.path.join(OUTPUT_DIR, "eggnog", "Update.txt"))], "524288")))
        f.close()

    print("Copying truffles...")

    # Truffles
    for truffle in os.listdir(os.path.join(INPUT_DIR, "Mib2", "Truffles")):
        rel_path = os.path.join(INPUT_DIR, "Mib2", "Truffles", truffle, "0", "default")
        for root, dirs, files in os.walk(os.path.join(INPUT_DIR, "Mib2", "Truffles", truffle, "0", "default")):
            for file in files:
                pre_do_file(os.path.join(root, file)[(len(INPUT_DIR) + 1):],
                            os.path.join("truffles", "db", truffle, os.path.join(root, file)[(len(rel_path) + 1):]))

    end_time = time.time()
    print("Done! Took " + str(int((end_time - start_time) * 10000) / 10000) + " seconds.")
    if len(errors) > 0:
        print("Errors: " + str(errors))
    else:
        print("No errors.")


if __name__ == "__main__":
    shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
    run()
