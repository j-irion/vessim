import pandas as pd
import argparse


def feather_to_csv(input_path, output_path=None):
    """
    Convert a Feather file to CSV.

    Args:
        input_path (str): Path to the input Feather file (.feather).
        output_path (str, optional): Path for the output CSV.
            If None, uses the input path with .csv extension.
    """
    # Read Feather file
    df = pd.read_feather(input_path)

    # Determine output path if not provided
    if output_path is None:
        output_path = input_path.replace(".feather", ".csv")

    # Write to CSV
    df.to_csv(output_path, index=True)
    print(f"Successfully converted {input_path} to {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert Feather file to CSV")
    parser.add_argument("input", help="Input Feather file path")
    parser.add_argument("--output", help="Output CSV file path (optional)")
    args = parser.parse_args()

    feather_to_csv(args.input, args.output)
