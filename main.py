from sys import exit


def main():
    pass


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"An error occurred: {e}")
        exit(1)
    finally:
        print("Game closing...")
