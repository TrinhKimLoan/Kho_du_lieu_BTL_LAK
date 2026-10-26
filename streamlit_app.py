"""Root entrypoint: keep the legacy app package unambiguous on Streamlit startup."""
from src.dashboard.ui import main

if __name__ == '__main__':
    main()
