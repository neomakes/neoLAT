
import subprocess
import plistlib
import time
import os
import sys

def debug_m4_power():
    # Request ALL samplers to see what's available
    # Excluding 'tasks' to keep output manageable, but including everything else relevant
    cmd = [
        "sudo", "powermetrics",
        "-n", "1",
        "--format", "plist",
        "--samplers", "cpu_power,gpu_power,ane_power,disk,network,battery"
    ]
    
    # Run command
    result = subprocess.run(cmd, capture_output=True, text=False) # Binary output for plist
    
    if result.returncode != 0:
        print(f"Error (Code {result.returncode}):")
        try:
            print(result.stderr.decode('utf-8'))
        except:
             print(result.stderr)
        print("\n[Hint] Did you run with 'sudo'?")
        return

    # Parse Plist
    try:
        # powermetrics output often has a null byte or header garbage before the plist
        # But usually --format plist gives a clean plist stream or multiple concatenated plists.
        # We only asked for 1 sample (-n 1).
        if len(result.stdout) < 10:
             print("Empty output from powermetrics")
             return

        data = plistlib.loads(result.stdout)
        
        # Print Keys nicely
        print("\n[Top Level Keys]")
        print(list(data.keys()))
        
        print("\n[Processor Info]")
        if "processor" in data:
            print(data["processor"])
        else:
             print(" 'processor' key not found.")

        print("\n[Device Power Domains]")
        for key in ['gpu', 'ane', 'cpu_power', 'dram']:
            if key in data:
                print(f"\n--- {key.upper()} ---")
                print(data[key])
            else:
                print(f" {key}: Not found at top level")
        
        print("\n[Full Raw Dump (for detailed inspection)]")
        print(data)
        
    except Exception as e:
        print(f"Error parsing Plist: {e}")
        print("Raw Output snippet:")
        print(result.stdout[:500])

if __name__ == "__main__":
    debug_m4_power()
