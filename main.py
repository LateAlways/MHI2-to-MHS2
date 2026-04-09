import json
import os
import sys
import shutil
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

OUTPUT_DIR = "Output"
INPUT_DIR = "Input"
MAX_WORKERS = os.cpu_count() or 4

_log_file = None
_old_print = print
_print_lock = threading.Lock()

# ANSI Colors
# Enable ANSI on Windows 10+
if sys.platform == "win32":
    os.system("")

RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
GREEN   = "\033[32m"
RED     = "\033[31m"
YELLOW  = "\033[33m"
CYAN    = "\033[36m"
MAGENTA = "\033[35m"
WHITE   = "\033[37m"
BG_GREEN = "\033[42m"
BG_RED   = "\033[41m"


def _strip_ansi(text):
    """Remove ANSI escape codes for the log file."""
    import re
    return re.sub(r"\033\[[0-9;]*m", "", text)


def print(*args, **kwargs):
    with _print_lock:
        _old_print(*args, **kwargs)
        # Write plain text (no color codes) to the log file
        stripped = _strip_ansi(" ".join(str(a) for a in args))
        _old_print(stripped, file=_log_file)


def copy_file_to_output(input_path, output_path):
    dest = os.path.join(OUTPUT_DIR, output_path)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy(os.path.join(INPUT_DIR, input_path), dest)


def detect_region():
    return [d for d in next(os.walk(os.path.join(INPUT_DIR, "Mib1", "Eggnog")))[1]
            if d not in ("DBInfo", "InfoFile")][0]


CONVERSION_PATHS = {
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
    "Mib2/NavDB/common_{region}/0/default/content.sig": "database/{region}/map/common/content.sig"
}


# Shared counters

class Stats:
    def __init__(self):
        self._lock = threading.Lock()
        self.copied = 0
        self.failed = 0
        self.errors = []
        self.section_times = {}

    def record_success(self):
        with self._lock:
            self.copied += 1

    def record_error(self, path, error):
        with self._lock:
            self.failed += 1
            self.errors.append((path, str(error)))


# Pretty helpers

def banner(title, icon="*"):
    width = 52
    print(f"\n{CYAN}{BOLD}  {icon}  {title}{RESET}")
    print(f"{DIM}  {'.' * width}{RESET}")


def section_done(label, count, elapsed):
    print(f"  {GREEN}OK{RESET}  {label}: {BOLD}{count}{RESET} files in {YELLOW}{elapsed:.2f}s{RESET}")


def file_ok(filename):
    short = os.path.basename(filename)
    print(f"  {DIM}  >{RESET} {short}")


def file_err(filename, error):
    short = os.path.basename(filename)
    print(f"  {RED}  x {short}  --  {error}{RESET}")


def run():
    stats = Stats()

    region = detect_region()
    REGION = region.upper()
    var_map = {"region": region, "REGION": REGION}

    def replace_vars(s):
        return s.format_map(var_map)

    print(f"\n{BOLD}{'=' * 56}{RESET}")
    print(f"{BOLD}   Maps Translator{RESET}")
    print(f"{'=' * 56}")
    print(f"  Region   : {CYAN}{BOLD}{REGION}{RESET}")
    print(f"  Workers  : {CYAN}{BOLD}{MAX_WORKERS}{RESET}")
    print(f"  Input    : {DIM}{os.path.abspath(INPUT_DIR)}{RESET}")
    print(f"  Output   : {DIM}{os.path.abspath(OUTPUT_DIR)}{RESET}")
    print(f"{'=' * 56}")

    def do_copy(input_path, output_path):
        """Thread-safe file copy."""
        input_path = input_path.replace("\\", "/")
        output_path = output_path.replace("\\", "/")
        try:
            copy_file_to_output(input_path, output_path)
            stats.record_success()
            file_ok(output_path)
            return True
        except Exception as e:
            stats.record_error(input_path, e)
            file_err(input_path, e)
            return False

    start_time = time.time()

    # Phase 1: Quick setup
    banner("Preparing directories", ">>")

    with open(os.path.join(INPUT_DIR, "Mib2", "NavDB", f"RegionList_{region}", "0", "default", "regionList.json")) as f:
        region_list_json = f.read().replace("/net/mmx/mnt/navdb/", "")

    os.makedirs(os.path.join(OUTPUT_DIR, "database", region), exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, "database", region, "regionList.json"), "w") as f:
        f.write(region_list_json)

    region_entries = json.loads(region_list_json)["regions"]
    for region_entry in region_entries:
        os.makedirs(os.path.join(OUTPUT_DIR, region_entry["directory"]))

    with open(os.path.join(INPUT_DIR, "Mib2", "SpeechResVDE", "regionList", "0", "default", "regionList.txt")) as f:
        region_list_converted = f.read().replace("/net/mmx/mnt/navdb/speech/sr/vde", ".")
    speech_vde_dir = os.path.join(OUTPUT_DIR, "speech", "sr", "vde")
    os.makedirs(speech_vde_dir, exist_ok=True)
    with open(os.path.join(speech_vde_dir, "regionList.txt"), "w") as f:
        f.write(region_list_converted)

    print(f"  {GREEN}OK{RESET}  Created {len(region_entries)} region directories")

    # Phase 2: Parallel I/O

    def task_general_files():
        t = time.time()
        banner("General Files", "01")
        futures = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            for inp, out in CONVERSION_PATHS.items():
                futures.append(pool.submit(do_copy, replace_vars(inp), replace_vars(out)))
            for fut in as_completed(futures):
                fut.result()
        section_done("General files", len(CONVERSION_PATHS), time.time() - t)

    def task_dbinfo():
        t = time.time()
        banner("Database Info", "02")
        dbinfo_src = os.path.join("Mib2", "NavDB", "DBInfo", "0", "default", "DBInfo.txt")
        do_copy(dbinfo_src, "DBInfo.txt")
        do_copy(dbinfo_src, os.path.join("database", "DBInfo.txt"))
        section_done("DBInfo", 2, time.time() - t)

    def task_translate_region_folder(folder):
        navdb_base = os.path.join("Mib2", "NavDB", f"{folder}_{region}", "0", "default")
        with open(os.path.join(INPUT_DIR, navdb_base, "content.pkg")) as f:
            content_pkg = json.load(f)

        out_folder = os.path.join("database", region, "map", "regions", folder)

        copy_futures = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            for content_file in content_pkg["file"]:
                name = content_file["name"]
                location = os.path.join(content_file["source"], name) if "source" in content_file else name
                copy_futures.append(
                    pool.submit(do_copy, os.path.join(navdb_base, location), os.path.join(out_folder, name))
                )
            for fut in as_completed(copy_futures):
                fut.result()

        content_pkg["file"] = [
            {k: v for k, v in cf.items() if k != "source"}
            for cf in content_pkg["file"]
            if os.path.exists(os.path.join(OUTPUT_DIR, out_folder, cf["name"]))
        ]
        with open(os.path.join(OUTPUT_DIR, out_folder, "content.pkg"), "w") as f:
            json.dump(content_pkg, f, indent=2)

        do_copy(os.path.join(navdb_base, "content.sig"), os.path.join(out_folder, "content.sig"))
        return len(copy_futures) + 1  # +1 for content.sig

    def task_translate_regions():
        t = time.time()
        banner("Region Translation", "03")
        regions_dir = os.path.join(OUTPUT_DIR, "database", region, "map", "regions")
        folders = os.listdir(regions_dir)
        total_files = 0
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {pool.submit(task_translate_region_folder, f): f for f in folders}
            for fut in as_completed(futures):
                total_files += fut.result()
        section_done(f"Regions ({len(folders)} folders)", total_files, time.time() - t)

    def task_speech_files():
        t = time.time()
        banner("Speech Files", "04")
        region_prefix = REGION + "_"
        futures = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            for folder in os.listdir(os.path.join(INPUT_DIR, "Mib2", "SpeechResVDE")):
                if folder.startswith(region_prefix):
                    speech_base = os.path.join("Mib2", "SpeechResVDE", folder, "0", "default")
                    subfolder = folder[len(region_prefix):]
                    for file in os.listdir(os.path.join(INPUT_DIR, speech_base)):
                        if not file.endswith("hashes.txt"):
                            futures.append(pool.submit(
                                do_copy,
                                os.path.join(speech_base, file),
                                os.path.join("speech", "sr", "vde", REGION, subfolder, file),
                            ))
            for fut in as_completed(futures):
                fut.result()
        section_done("Speech", len(futures), time.time() - t)

    def task_truffles():
        t = time.time()
        banner("Truffles", "05")
        futures = []
        input_prefix_len = len(INPUT_DIR) + 1
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            for truffle in os.listdir(os.path.join(INPUT_DIR, "Mib2", "Truffles")):
                truffle_base = os.path.join(INPUT_DIR, "Mib2", "Truffles", truffle, "0", "default")
                base_len = len(truffle_base) + 1
                for root, dirs, files in os.walk(truffle_base):
                    for file in files:
                        if not file.endswith("hashes.txt"):
                            full = os.path.join(root, file)
                            futures.append(pool.submit(
                                do_copy,
                                full[input_prefix_len:],
                                os.path.join("truffles", "db", truffle, full[base_len:]),
                            ))
            for fut in as_completed(futures):
                fut.result()
        section_done("Truffles", len(futures), time.time() - t)

    # Launch all sections in parallel
    section_tasks = [
        task_general_files,
        task_dbinfo,
        task_translate_regions,
        task_speech_files,
        task_truffles,
    ]
    with ThreadPoolExecutor(max_workers=len(section_tasks)) as section_pool:
        section_futures = {section_pool.submit(task): task.__name__ for task in section_tasks}
        for fut in as_completed(section_futures):
            name = section_futures[fut]
            try:
                fut.result()
            except Exception as e:
                print(f"\n  {RED}{BOLD}FAIL{RESET}  Section '{name}' crashed: {e}")

    # Summary
    elapsed = time.time() - start_time

    print(f"\n{'=' * 56}")
    if stats.failed == 0:
        print(f"  {BG_GREEN}{BOLD} COMPLETE {RESET}  "
              f"{GREEN}{stats.copied}{RESET} files copied  |  "
              f"{YELLOW}{elapsed:.2f}s{RESET}")
    else:
        print(f"  {BG_RED}{BOLD} COMPLETE WITH ERRORS {RESET}  "
              f"{GREEN}{stats.copied} copied{RESET}  |  "
              f"{RED}{stats.failed} failed{RESET}  |  "
              f"{YELLOW}{elapsed:.2f}s{RESET}")
        print(f"\n  {RED}{BOLD}Failed files:{RESET}")
        for path, err in stats.errors:
            print(f"    {RED}x{RESET} {path}")
            print(f"      {DIM}{err}{RESET}")
    print(f"{'=' * 56}\n")


if __name__ == "__main__":
    shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
    if os.path.exists("log.txt"):
        os.remove("log.txt")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    _log_file = open("log.txt", "a")
    try:
        run()
    finally:
        _log_file.close()
