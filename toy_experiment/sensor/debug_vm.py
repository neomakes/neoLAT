
import subprocess
import re

def test_vmstat_parsing():
    try:
        out = subprocess.check_output(["vm_stat"], text=True)
        print("--- vm_stat output ---")
        print(out)
        print("----------------------")
        
        sample = {}
        for line in out.splitlines():
            if "Pageouts" in line: sample["pageouts"] = int(line.split(":")[1].strip().strip('.'))
            if "Pageins" in line: sample["pageins"] = int(line.split(":")[1].strip().strip('.'))
            if "COW-faults" in line: sample["cow_faults"] = int(line.split(":")[1].strip().strip('.'))
            if "Translation faults" in line: sample["faults"] = int(line.split(":")[1].strip().strip('.'))
            if "Pages stored in compressor" in line: sample["compressed_pages"] = int(line.split(":")[1].strip().strip('.'))

        print(f"Parsed sample: {sample}")
        
        page_size = 16384
        if "compressed_pages" in sample:
            compressed_mb = (sample["compressed_pages"] * page_size) / (1024**2)
            print(f"Calculated compressed_mb: {compressed_mb}")
        else:
            print("compressed_pages NOT FOUND")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_vmstat_parsing()
