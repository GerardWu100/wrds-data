import sys
import os

def main():
    if len(sys.argv) < 2:
        print("Usage: python check_max_last_col.py <filename>")
        print("Example: python check_max_last_col.py SPY_full_1min_adjsplitdiv.txt")
        sys.exit(1)

    filename = sys.argv[1]
    
    try:
        if not os.path.isfile(filename):
            print(f"Error: Could not find file {filename}")
            sys.exit(1)

        max_val = float('-inf')
        
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                parts = line.split(',')
                val_str = parts[-1].strip()
                
                try:
                    val = float(val_str)
                    if val > max_val:
                        max_val = val
                except ValueError:
                    pass
                        
        if max_val != float('-inf'):
            print(f"File: {filename}")
            print(f"Maximum value in last column: {max_val}")
        else:
            print("No valid numeric data found in the last column.")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
