# Jupyter CPP Kernel

This project was forked from <https://github.com/brendan-rius/jupyter-c-kernel> to let it work with C++. **Original README is appended below.**

The main purpose of this project is to let myself allow to notetake CSE lectures with relevant code that can be executed in the notebook. So it might not be suitable for the people who demands a full-featured C++ kernel for production.

It includes a few improvements:

**You can include another cpp file in your workspace with the `#include` directive.** 

Example code is provided in the `examples` folder. Keep in mind that cpp file and header file should be in a same level of directory. In other words, it's not allowed to have a header file in include directory and cpp file in src directory. Instead, you should have both in the same directory.

**Minor refactoring**

There were some minor refactoring in both cpp and python code.

## Pre-requisites

1. gcc
2. Jupyter Notebook

## Installation

```bash
git clone https://github.com/01Joseph-Hwang10/jupyter-cpp-kernel
cd jupyter-cpp-kernel
pip install -r requirements.txt # Recommend to use virtualenv
cd jupyter_cpp_kernel
sudo python install_cpp_kernel
```

Make sure to reload the jupyter notebook after installation if there are existing running notebooks.

## Note

- This kernel was tested on:
  - M1 Macbook Air
  - OS: macOS Ventura 13.1
  - RAM: 16GB
  - gcc is provided by Xcode
- I did not tested the Dockerfile, so it might not work.

## Limitations

It cannot:
- recieve input from prompt like python `input` function. It will simply return an empty string.

## Custom compilation flags

Everything is same as original README (see `## Custom complication flags` section below), except `cflags` is replaced with `cxxflags`.

```cpp
//%cxxflags: -Wall -g

#include <iostream>

int main() {
   std::cout << "Hello world!" << std::endl;
   return 0;
}
```

# Origianl README

Check out the original README for further details: <https://github.com/brendan-rius/jupyter-c-kernel#readme>