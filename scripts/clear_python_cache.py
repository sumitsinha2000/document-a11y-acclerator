#!/usr/bin/env python3
"""
Clear Python bytecode cache to ensure latest code is used
"""
import os
import shutil
from pathlib import Path

def clear_pycache():
    """Remove all __pycache__ directories and .pyc files"""
    backend_dir = Path(__file__).parent.parent / 'backend'
    
    removed_count = 0
    
    # Remove __pycache__ directories
    for pycache_dir in backend_dir.rglob('__pycache__'):
        print(f"Removing: {pycache_dir}")
        shutil.rmtree(pycache_dir)
        removed_count += 1
    
    # Remove .pyc files
    for pyc_file in backend_dir.rglob('*.pyc'):
        print(f"Removing: {pyc_file}")
        pyc_file.unlink()
        removed_count += 1
    
    print(f"\nCleared {removed_count} cache files/directories")
    print("Python cache cleared successfully!")

if __name__ == '__main__':
    clear_pycache()
