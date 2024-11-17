import hashlib


class HashesFile:
    def __init__(self, FileName: str=None, Destination: str=None, FileSize: str=None, CheckSums: list=None, CheckSumSize: str=None):
        self.FileName = FileName
        self.Destination = Destination
        self.FileSize = FileSize
        self.CheckSumSize = CheckSumSize
        self.CheckSums = CheckSums

    def __str__(self):
        out = ""
        if self.FileName is not None:
            out += f"FileName = \"{self.FileName}\"\n"
        if self.Destination is not None:
            out += f"Destination = \"{self.Destination}\"\n"
        if self.FileSize is not None:
            out += f"FileSize = \"{self.FileSize}\"\n"
        if self.CheckSumSize is not None:
            out += f"CheckSumSize = \"{self.CheckSumSize}\"\n"
        for i, checksum in enumerate(self.CheckSums):
            out += "CheckSum"
            if i != 0:
                out += f"{i}"

            out += f" = \"{checksum}\"\n"

        return out+"\n"

def generate_checksum(file: str, checksumsize: int=524288) -> list:
    hashes = []
    with open(file, 'rb') as f:
        while True:
            checksum = hashlib.sha1()
            data = f.read(checksumsize)
            if not data:
                break
            checksum.update(data)
            hashes.append(checksum.hexdigest())
    return hashes

def parse_hashes_file(file: str):
    hashes = []
    with open(file, "r") as f:
        hashes_text = f.read().split("\n\n")[:-1]
        CheckSums = []
        FileName = None
        FileSize = None
        Destination = None
        CheckSumSize = None
        for hash in hashes_text:
            lines = hash.split("\n")
            for line in lines:
                if line[:8] == "FileName":
                    FileName = line[12:-1]
                elif line[:11] == "Destination":
                    Destination = line[15:-1]
                elif line[:8] == "FileSize":
                    FileSize = line[12:-1]
                elif line[:12] == "CheckSumSize":
                    CheckSumSize = line[16:-1]
                elif line[:8] == "CheckSum":
                    CheckSums.append(line[12:-1]) if len(CheckSums) == 0 else CheckSums.append(line[12+len(str(len(CheckSums))):-1])

            hashes.append(HashesFile(FileName, Destination, FileSize, CheckSums, CheckSumSize))
    return hashes
