from app.analysis.imports import extract_added_dependencies, extract_added_imports


def patch(*lines: str) -> str:
    return "@@ -1,3 +1,6 @@\n" + "\n".join(lines)


def test_only_added_lines_count():
    p = patch("-import React from 'react'", " import vue from 'vue'", "+import axios from 'axios'")
    assert extract_added_imports("TypeScript", p) == {"axios"}


def test_javascript_forms_and_normalisation():
    p = patch(
        "+import { createRoot } from 'react-dom/client'",
        "+} from '@reduxjs/toolkit/query'",
        "+const express = require('express')",
        "+import './styles.css'",
        "+import Button from './Button'",
        "+import fs from 'node:fs'",
        "+const Page = lazy(() => import('@/pages/Home'))",
    )
    assert extract_added_imports("JavaScript", p) == {"react-dom", "@reduxjs/toolkit", "express", "node"}


def test_python_forms():
    p = patch(
        "+from fastapi import FastAPI",
        "+import numpy as np, pandas as pd",
        "+from sklearn.model_selection import train_test_split",
        "+from .models import User",
        "+    import torch.nn",
    )
    assert extract_added_imports("Python", p) == {"fastapi", "numpy", "pandas", "sklearn", "torch"}


def test_notebook_json_lines():
    p = patch('+    "import pandas as pd\\n",', '+    "from matplotlib import pyplot\\n"')
    assert extract_added_imports("Jupyter Notebook", p) == {"pandas", "matplotlib"}


def test_other_languages():
    assert extract_added_imports("Go", patch('+import "github.com/gin-gonic/gin/binding"', '+\t"net/http"')) == {
        "github.com/gin-gonic/gin",
        "net/http",
    }
    assert extract_added_imports("Java", patch("+import org.springframework.boot.SpringApplication;")) == {
        "org.springframework.boot.SpringApplication"
    }
    assert extract_added_imports("Rust", patch("+use tokio::sync::Mutex;", "+use crate::db;")) == {"tokio"}
    assert extract_added_imports("Dart", patch("+import 'package:flutter/material.dart';")) == {"flutter"}


def test_package_json_dependencies_ignore_scripts_and_metadata():
    p = patch(
        '+  "version": "0.1.0",',
        '+  "dev": "vite",',
        '+    "react": "^18.3.1",',
        '+    "@tanstack/react-query": "~5.0.0",',
        '+    "tailwindcss": "latest"',
    )
    assert extract_added_dependencies("frontend/package.json", p) == {"react", "@tanstack/react-query", "tailwindcss"}


def test_python_and_other_manifests():
    assert extract_added_dependencies("requirements.txt", patch("+fastapi>=0.111", "+uvicorn[standard]", "+# comment", "+-r base.txt")) == {
        "fastapi",
        "uvicorn",
    }
    assert extract_added_dependencies("pyproject.toml", patch('+    "django>=5",', '+name = "app"', '+flask = "^3.0"')) == {
        "django",
        "flask",
    }
    assert extract_added_dependencies("go.mod", patch("+\tgithub.com/gin-gonic/gin v1.9.1")) == {"github.com/gin-gonic/gin"}
    assert extract_added_dependencies("pom.xml", patch("+    <artifactId>spring-boot-starter-web</artifactId>")) == {
        "spring-boot-starter-web"
    }
