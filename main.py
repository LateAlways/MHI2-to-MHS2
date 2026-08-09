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
# File copying is I/O bound, so the copy pool oversubscribes the CPU count.
COPY_WORKERS = max(8, MAX_WORKERS * 4)

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


# Folders under Mib1/Eggnog that hold archive-wide data instead of a region
NON_REGION_DIRS = ("DBInfo", "InfoFile")


def subdirs(path):
    return next(os.walk(path))[1] if os.path.isdir(path) else []


def detect_regions():
    """Every region code shipped in the input archive.

    EU archives contain a single region, RoW archives contain several (asia,
    aus, il, india, meast, msa, msa2, neast, za). Regions are read from
    Mib1/Eggnog and cross-checked against Mib2/NavDB/RegionList_* so a region
    listed by only one of the two is still converted.

    Returns (regions, mismatched) where `mismatched` holds the codes that only
    one of the two sources knows about.
    """
    eggnog = {d for d in subdirs(os.path.join(INPUT_DIR, "Mib1", "Eggnog"))
              if d not in NON_REGION_DIRS}
    prefix = "RegionList_"
    navdb = {d[len(prefix):] for d in subdirs(os.path.join(INPUT_DIR, "Mib2", "NavDB"))
             if d.startswith(prefix)}
    regions = sorted(eggnog | navdb)
    if not regions:
        raise RuntimeError(f"No regions found under {os.path.join(INPUT_DIR, 'Mib1', 'Eggnog')}")
    return regions, sorted(eggnog ^ navdb)


# Copied once per region. {region} is the code as-is, {REGION} its upper case.
REGION_CONVERSION_PATHS = {
    "Mib1/Eggnog/{region}/0/default/EggnogDB.ser": "database/{region}/eggnog/eggnog_light/EggnogDB.ser",
    "Mib2/NavDB/common_{region}/0/default/CountryBorders_WorldCartographicLayer_Basic.psf": "database/{region}/map/common/CountryBorders_WorldCartographicLayer_Basic.psf",
    "Mib2/NavDB/common_{region}/0/default/DTM_{REGION}_Texture.psf": "database/{region}/map/common/DTM_{REGION}_Texture.psf",
    "Mib2/NavDB/common_{region}/0/default/Topomap_{REGION}_Texture.psf": "database/{region}/map/common/Topomap_{REGION}_Texture.psf",
    "Mib2/NavDB/common_{region}/0/default/Topomap_World_Texture.psf": "database/{region}/map/common/Topomap_World_Texture.psf",
    "Mib2/NavDB/common_{region}/0/default/WorldCartographicLayer_Basic.psf": "database/{region}/map/common/WorldCartographicLayer_Basic.psf",
    "Mib2/NavDB/common_{region}/0/default/content.pkg": "database/{region}/map/common/content.pkg",
    "Mib2/NavDB/common_{region}/0/default/content.sig": "database/{region}/map/common/content.sig"
}

# Copied once for the whole archive, regardless of how many regions it holds
GLOBAL_CONVERSION_PATHS = {
    "Mib1/Eggnog/DBInfo/0/default/EggnogDBInfo.txt": "eggnog/EggnogDBInfo.txt",
    "Mib1/Eggnog/InfoFile/0/default/Update.txt": "eggnog/Update.txt",
    "Mib2/SpeechResVDE/InfoFile/0/default/Update.txt": "speech/sr/vde/Update.txt"
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


def region_ok(region, message):
    print(f"  {GREEN}OK{RESET}  {CYAN}{region.upper()}{RESET}: {message}")


def region_warn(region, message):
    print(f"  {YELLOW}--{RESET}  {CYAN}{region.upper()}{RESET}: {message}")


def region_err(region, message):
    print(f"  {RED}x {RESET}  {CYAN}{region.upper()}{RESET}: {RED}{message}{RESET}")


def run():
    stats = Stats()

    regions, mismatched = detect_regions()

    print(f"\n{BOLD}{'=' * 56}{RESET}")
    print(f"{BOLD}   Maps Translator{RESET}")
    print(f"{'=' * 56}")
    print(f"  Regions  : {CYAN}{BOLD}{', '.join(r.upper() for r in regions)}{RESET} ({len(regions)})")
    print(f"  Workers  : {CYAN}{BOLD}{MAX_WORKERS}{RESET}")
    print(f"  Input    : {DIM}{os.path.abspath(INPUT_DIR)}{RESET}")
    print(f"  Output   : {DIM}{os.path.abspath(OUTPUT_DIR)}{RESET}")
    print(f"{'=' * 56}")
    if mismatched:
        print(f"  {YELLOW}!{RESET}  Only in one of Eggnog / NavDB: "
              f"{YELLOW}{', '.join(r.upper() for r in mismatched)}{RESET}")

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

    # Every region gets its own regionList.json and its own map/regions tree.
    prepared_regions = []
    total_region_dirs = 0
    for region in regions:
        navdb_regionlist = os.path.join(INPUT_DIR, "Mib2", "NavDB", f"RegionList_{region}",
                                        "0", "default", "regionList.json")
        try:
            with open(navdb_regionlist) as f:
                region_list_json = f.read().replace("/net/mmx/mnt/navdb/", "")

            region_db_dir = os.path.join(OUTPUT_DIR, "database", region)
            os.makedirs(region_db_dir, exist_ok=True)
            with open(os.path.join(region_db_dir, "regionList.json"), "w") as f:
                f.write(region_list_json)

            region_entries = json.loads(region_list_json)["regions"]
            for region_entry in region_entries:
                os.makedirs(os.path.join(OUTPUT_DIR, region_entry["directory"]), exist_ok=True)

            prepared_regions.append(region)
            total_region_dirs += len(region_entries)
            region_ok(region, f"{len(region_entries)} region directories")
        except Exception as e:
            stats.record_error(navdb_regionlist, e)
            region_err(region, e)

    # The speech region list is archive-wide. EU ships a single "regionList"
    # folder; if a multi-region archive splits it per region, merge the parts.
    speech_root = os.path.join(INPUT_DIR, "Mib2", "SpeechResVDE")
    speech_regionlists = sorted(d for d in subdirs(speech_root) if d.lower().startswith("regionlist"))
    speech_lines = []
    for speech_folder in speech_regionlists:
        src = os.path.join(speech_root, speech_folder, "0", "default", "regionList.txt")
        try:
            with open(src) as f:
                text = f.read().replace("/net/mmx/mnt/navdb/speech/sr/vde", ".")
        except Exception as e:
            stats.record_error(src, e)
            file_err(src, e)
            continue
        for line in text.splitlines():
            if line not in speech_lines:
                speech_lines.append(line)

    if speech_lines:
        speech_vde_dir = os.path.join(OUTPUT_DIR, "speech", "sr", "vde")
        os.makedirs(speech_vde_dir, exist_ok=True)
        with open(os.path.join(speech_vde_dir, "regionList.txt"), "w") as f:
            f.write("\n".join(speech_lines) + "\n")
        if len(speech_regionlists) > 1:
            print(f"  {GREEN}OK{RESET}  Merged {len(speech_regionlists)} speech region lists "
                  f"into {len(speech_lines)} entries")
    else:
        print(f"  {YELLOW}--{RESET}  No speech region list found under {speech_root}")

    print(f"  {GREEN}OK{RESET}  Created {total_region_dirs} region directories "
          f"across {len(prepared_regions)}/{len(regions)} regions")

    # Phase 2: Parallel I/O
    #
    # One shared pool performs every file copy. Orchestration tasks (sections
    # and per-folder work) run in their own pools, so a task blocking on a copy
    # future can never starve the pool that has to complete it.
    copy_pool = ThreadPoolExecutor(max_workers=COPY_WORKERS)

    def task_general_files():
        t = time.time()
        banner("General Files", "01")
        jobs = list(GLOBAL_CONVERSION_PATHS.items())
        for region in regions:
            var_map = {"region": region, "REGION": region.upper()}
            jobs += [(inp.format_map(var_map), out.format_map(var_map))
                     for inp, out in REGION_CONVERSION_PATHS.items()]

        futures = [copy_pool.submit(do_copy, inp, out) for inp, out in jobs]
        for fut in as_completed(futures):
            fut.result()
        section_done(f"General files ({len(regions)} regions)", len(jobs), time.time() - t)

    def task_dbinfo():
        t = time.time()
        banner("Database Info", "02")
        dbinfo_src = os.path.join("Mib2", "NavDB", "DBInfo", "0", "default", "DBInfo.txt")
        do_copy(dbinfo_src, "DBInfo.txt")
        do_copy(dbinfo_src, os.path.join("database", "DBInfo.txt"))
        section_done("DBInfo", 2, time.time() - t)

    def task_translate_region_folder(region, folder):
        navdb_base = os.path.join("Mib2", "NavDB", f"{folder}_{region}", "0", "default")
        with open(os.path.join(INPUT_DIR, navdb_base, "content.pkg")) as f:
            content_pkg = json.load(f)

        out_folder = os.path.join("database", region, "map", "regions", folder)

        copy_futures = []
        for content_file in content_pkg["file"]:
            name = content_file["name"]
            location = os.path.join(content_file["source"], name) if "source" in content_file else name
            copy_futures.append(
                copy_pool.submit(do_copy, os.path.join(navdb_base, location),
                                 os.path.join(out_folder, name))
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

        # Each region owns its own set of map folders, and the NavDB source
        # folder is named "<folder>_<region>" -- so folders must stay paired
        # with the region they came from.
        folder_jobs = []
        for region in prepared_regions:
            regions_dir = os.path.join(OUTPUT_DIR, "database", region, "map", "regions")
            if not os.path.isdir(regions_dir):
                region_warn(region, "no map/regions folders")
                continue
            folder_jobs += [(region, folder) for folder in sorted(os.listdir(regions_dir))]

        total_files = 0
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {pool.submit(task_translate_region_folder, region, folder): (region, folder)
                       for region, folder in folder_jobs}
            for fut in as_completed(futures):
                region, folder = futures[fut]
                try:
                    total_files += fut.result()
                except Exception as e:
                    stats.record_error(f"{folder}_{region}", e)
                    file_err(f"{folder}_{region}", e)
        section_done(f"Regions ({len(folder_jobs)} folders across {len(prepared_regions)} regions)",
                     total_files, time.time() - t)

    def task_speech_files():
        t = time.time()
        banner("Speech Files", "04")
        speech_folders = os.listdir(os.path.join(INPUT_DIR, "Mib2", "SpeechResVDE"))
        futures = []
        for region in regions:
            REGION = region.upper()
            region_prefix = REGION + "_"
            before = len(futures)
            for folder in speech_folders:
                if not folder.startswith(region_prefix):
                    continue
                speech_base = os.path.join("Mib2", "SpeechResVDE", folder, "0", "default")
                subfolder = folder[len(region_prefix):]
                for file in os.listdir(os.path.join(INPUT_DIR, speech_base)):
                    if not file.endswith("hashes.txt"):
                        futures.append(copy_pool.submit(
                            do_copy,
                            os.path.join(speech_base, file),
                            os.path.join("speech", "sr", "vde", REGION, subfolder, file),
                        ))
            if len(futures) == before:
                region_warn(region, "no speech resources")

        for fut in as_completed(futures):
            fut.result()
        section_done("Speech", len(futures), time.time() - t)

    def task_truffles():
        t = time.time()
        banner("Truffles", "05")
        futures = []
        input_prefix_len = len(INPUT_DIR) + 1
        for truffle in os.listdir(os.path.join(INPUT_DIR, "Mib2", "Truffles")):
            truffle_base = os.path.join(INPUT_DIR, "Mib2", "Truffles", truffle, "0", "default")
            base_len = len(truffle_base) + 1
            for root, dirs, files in os.walk(truffle_base):
                for file in files:
                    if not file.endswith("hashes.txt"):
                        full = os.path.join(root, file)
                        futures.append(copy_pool.submit(
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
    try:
        with ThreadPoolExecutor(max_workers=len(section_tasks)) as section_pool:
            section_futures = {section_pool.submit(task): task.__name__ for task in section_tasks}
            for fut in as_completed(section_futures):
                name = section_futures[fut]
                try:
                    fut.result()
                except Exception as e:
                    print(f"\n  {RED}{BOLD}FAIL{RESET}  Section '{name}' crashed: {e}")
    finally:
        copy_pool.shutdown(wait=True)

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
