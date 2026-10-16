"""Table-driven tests for the skill matcher: whole-token, ecosystem-aware matching.

Each case is one changed file (path + added lines) run through the real pipeline
(``build_contribution`` -> ``skills_for_contribution``), so import extraction,
manifest parsing and the rule keys are all exercised together.
"""

import pytest

from app.analysis.contribution import build_contribution
from app.analysis.skills import _matches, load_rules, skills_for_contribution


def skills_for(path: str, *added: str) -> set[str]:
    patch = "@@ -0,0 +1 @@\n" + "\n".join(f"+{line}" for line in added)
    c = build_contribution(
        kind="commit", repo="ana/app", external=False, url="https://github.com/ana/app/commit/abc",
        message="feat: change", date="2026-08-01T00:00:00Z",
        files=[{"filename": path, "additions": max(len(added), 1), "deletions": 0, "patch": patch}],
    )
    assert c is not None
    return set(skills_for_contribution(c, load_rules()))


# (case id, path, added lines, skills that must be detected, skills that must NOT be detected)
CASES = [
    # React family: react-native and testing-library are not React.
    ("react-import", "src/App.tsx", ["import { useState } from 'react'"], {"React"}, {"React Native"}),
    ("react-dom-client", "src/main.tsx", ["import { createRoot } from 'react-dom/client'"], {"React"}, set()),
    ("react-native-not-react", "app/styles.ts", ["import { StyleSheet } from 'react-native'"], {"React Native"}, {"React"}),
    ("react-native-dep-not-react", "package.json", ['    "react-native": "0.74.1",'], {"React Native"}, {"React"}),
    ("rn-community", "app/Store.ts", ["import AsyncStorage from '@react-native-community/async-storage'"], {"React Native"}, {"React"}),
    ("testing-library-not-react", "src/App.test.tsx", ["import { render } from '@testing-library/react'"], {"Automated Testing"}, {"React"}),
    ("react-redux-is-redux", "src/store.ts", ["import { Provider } from 'react-redux'"], {"Redux"}, {"React"}),
    ("react-query-not-react", "src/api.ts", ["import { useQuery } from '@tanstack/react-query'"], {"TanStack Query"}, {"React"}),
    ("react-bootstrap", "src/Nav.tsx", ["import Navbar from 'react-bootstrap/Navbar'"], {"Bootstrap"}, {"React"}),
    # Next.js family: next-auth is not Next.js; @next/* is.
    ("next-import", "pages/index.tsx", ["import Link from 'next/link'"], {"Next.js"}, {"NextAuth.js"}),
    ("next-auth-not-next", "lib/auth.ts", ["import NextAuth from 'next-auth'"], {"NextAuth.js", "OAuth / Authentication"}, {"Next.js"}),
    ("next-auth-dep-not-next", "package.json", ['    "next-auth": "^4.24.7",'], {"NextAuth.js"}, {"Next.js"}),
    ("next-scoped", "app/layout.tsx", ["import { Inter } from '@next/font/google'"], {"Next.js"}, set()),
    ("nextui-not-next", "src/Button.tsx", ["import { Button } from '@nextui-org/react'"], set(), {"Next.js", "React"}),
    ("next-config-path", "next.config.mjs", ["export default {}"], {"Next.js"}, set()),
    # Vue / Svelte / Angular siblings.
    ("vue-router-is-vue", "src/router.ts", ["import { createRouter } from 'vue-router'"], {"Vue.js"}, {"Nuxt"}),
    ("sveltekit", "src/routes/+page.ts", ["import { error } from '@sveltejs/kit'"], {"SvelteKit"}, {"Svelte"}),
    ("angular-material-not-core", "src/app.ts", ["import { MatButton } from '@angular/material/button'"], set(), {"Angular"}),
    ("angular-core", "src/app.component.ts", ["import { Component } from '@angular/core'"], {"Angular"}, set()),
    # Python: whole-module matching; families only where opted in.
    ("django-orm", "shop/models.py", ["from django.db import models"], {"Django", "Python"}, set()),
    ("drf", "api/views.py", ["from rest_framework.views import APIView"], {"Django"}, set()),
    ("django-ext-dep", "requirements.txt", ["django-environ==0.11.2"], {"Django"}, set()),
    ("flask-ext", "app/db.py", ["from flask_sqlalchemy import SQLAlchemy"], {"Flask"}, {"SQLAlchemy"}),
    ("fastapi", "api/main.py", ["from fastapi import FastAPI"], {"FastAPI"}, {"Flask", "Django"}),
    ("torch", "train.py", ["import torch.nn as nn"], {"PyTorch"}, {"TensorFlow"}),
    ("torchvision", "data.py", ["from torchvision import transforms"], {"PyTorch"}, set()),
    ("langchain-split-pkg", "rag/chain.py", ["from langchain_openai import ChatOpenAI"], {"LangChain"}, {"OpenAI API"}),
    ("langchain-js", "src/rag.ts", ["import { ChatPromptTemplate } from '@langchain/core/prompts'"], {"LangChain"}, set()),
    ("llama-index", "rag/index.py", ["from llama_index.core import VectorStoreIndex"], {"LlamaIndex"}, {"LangChain"}),
    ("llama-index-dep", "requirements.txt", ["llama-index-llms-openai==0.1.0"], {"LlamaIndex"}, set()),
    ("vector-store", "rag/store.py", ["import chromadb"], {"RAG / Vector Search"}, set()),
    ("gcp-namespace", "jobs/upload.py", ["from google.cloud import storage"], {"GCP"}, {"Azure"}),
    ("protobuf-not-gcp", "proto/msg_util.py", ["from google.protobuf import json_format"], set(), {"GCP"}),
    ("azure-namespace", "jobs/blob.py", ["from azure.storage.blob import BlobServiceClient"], {"Azure"}, {"GCP"}),
    ("pytest-plugin-dep", "requirements-dev.txt", ["pytest-asyncio==0.23.0"], {"Automated Testing"}, set()),
    ("redis-py", "cache.py", ["import redis"], {"Redis"}, set()),
    ("kafka-python", "events/consumer.py", ["from kafka import KafkaConsumer"], {"Kafka"}, set()),
    ("elasticsearch-py", "search/index.py", ["from elasticsearch import Elasticsearch"], {"Elasticsearch"}, set()),
    # JVM: package hierarchy matches, Gradle group:artifact matches, sibling words don't.
    ("spring-boot-import", "src/main/java/com/x/App.java", ["import org.springframework.boot.SpringApplication;"], {"Spring Boot", "Spring Framework", "Java"}, set()),
    ("spring-web-not-boot", "src/main/java/com/x/Api.java", ["import org.springframework.web.bind.annotation.RestController;"], {"Spring Framework"}, {"Spring Boot"}),
    ("spring-boot-starter-pom", "pom.xml", ["    <artifactId>spring-boot-starter-web</artifactId>"], {"Spring Boot", "Maven"}, set()),
    ("kafka-gradle", "build.gradle", ["    implementation 'org.apache.kafka:kafka-clients:3.7.0'"], {"Kafka", "Gradle"}, set()),
    ("spring-kafka-import", "src/main/java/com/x/Listener.java", ["import org.springframework.kafka.annotation.KafkaListener;"], {"Kafka", "Spring Framework"}, {"Spring Boot"}),
    ("android-kotlin", "app/src/main/java/com/x/MainActivity.kt", ["import androidx.appcompat.app.AppCompatActivity"], {"Android", "Kotlin"}, {"Jetpack Compose"}),
    ("compose", "app/src/main/java/com/x/Home.kt", ["import androidx.compose.material3.Text"], {"Jetpack Compose", "Android"}, set()),
    ("android-manifest", "app/src/main/AndroidManifest.xml", ['<manifest package="com.x">'], {"Android"}, set()),
    ("kotlinx-coroutines", "src/Main.kt", ["import kotlinx.coroutines.launch"], {"Kotlin"}, {"Android"}),
    # .NET
    ("aspnet", "Api/Program.cs", ["using Microsoft.AspNetCore.Builder;"], {".NET", "ASP.NET Core", "C#"}, {"Entity Framework"}),
    ("efcore-csproj", "Api/Api.csproj", ['    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="8.0.4" />'], {"Entity Framework", ".NET"}, set()),
    # Go: full module paths.
    ("gin", "cmd/server/main.go", ['import "github.com/gin-gonic/gin"'], {"Gin", "Go"}, {"Echo"}),
    ("sarama", "internal/bus/producer.go", ['import "github.com/IBM/sarama"'], {"Kafka"}, set()),
    ("go-gcp", "internal/store/gcs.go", ['import "cloud.google.com/go/storage"'], {"GCP"}, set()),
    ("go-mod-path", "go.mod", ["module github.com/ana/app"], {"Go"}, set()),
    # Ruby / Rails: rails-* helper gems are not Rails.
    ("rails-require", "config/application.rb", ["require 'rails/all'"], {"Ruby on Rails"}, set()),
    ("rails-sanitizer-not-rails", "Gemfile", ["gem 'rails-html-sanitizer'"], set(), {"Ruby on Rails"}),
    ("rails-gem", "Gemfile", ["gem 'rails', '~> 7.1'"], {"Ruby on Rails"}, set()),
    # Mobile: Flutter and Swift.
    ("flutter-material", "lib/main.dart", ["import 'package:flutter/material.dart';"], {"Flutter", "Dart"}, set()),
    ("flutter-bloc-pubspec", "pubspec.yaml", ["  flutter_bloc: ^8.1.3"], {"Flutter"}, set()),
    ("pubspec-sdk-key-ignored", "pubspec.yaml", ["  sdk: '>=3.0.0 <4.0.0'"], set(), {"Flutter"}),
    ("swiftui", "App/ContentView.swift", ["import SwiftUI"], {"SwiftUI", "Swift"}, {"UIKit"}),
    # Infra and paths.
    ("dockerfile", "Dockerfile", ["FROM python:3.12-slim"], {"Docker"}, set()),
    ("terraform", "infra/main.tf", ['resource "aws_s3_bucket" "b" {}'], {"Terraform"}, set()),
    ("gh-actions", ".github/workflows/ci.yml", ["on: [push]"], {"GitHub Actions", "CI/CD"}, set()),
    ("aws-sdk-v3", "src/s3.ts", ["import { S3Client } from '@aws-sdk/client-s3'"], {"AWS"}, {"DynamoDB"}),
    ("dynamodb", "src/db.ts", ["import { DynamoDBClient } from '@aws-sdk/client-dynamodb'"], {"DynamoDB", "AWS"}, set()),
    # Express is Node.js; express-like names are not.
    ("express", "server/index.js", ["const express = require('express')"], {"Express", "Node.js"}, set()),
    ("expression-parser-not-express", "src/calc.ts", ["import { parse } from 'expression-eval'"], set(), {"Express", "Node.js"}),
]


@pytest.mark.parametrize("path, added, present, absent", [c[1:] for c in CASES], ids=[c[0] for c in CASES])
def test_skill_matcher_table(path, added, present, absent):
    found = skills_for(path, *added)
    assert present <= found, f"missing {present - found}; got {sorted(found)}"
    assert not (absent & found), f"false positive {absent & found}"


def test_table_has_at_least_forty_cases():
    assert len(CASES) >= 40


@pytest.mark.parametrize(
    "value, key, expected",
    [
        ("react", "react", True),
        ("react-native", "react", False),
        ("react_native", "react", False),
        ("@aws-sdk/client-s3", "@aws-sdk", True),
        ("org.springframework.boot.SpringApplication", "org.springframework", True),
        ("org.apache.kafka:kafka-clients", "org.apache.kafka", True),
        ("django-environ", "django-*", True),
        ("djangoish", "django-*", False),
        ("React", "react", True),
    ],
)
def test_matches_primitive(value, key, expected):
    assert _matches(value, key) is expected


def test_rules_file_is_well_formed():
    rules = load_rules()
    assert len(rules) >= 120
    allowed = {"imports", "dependencies", "paths", "categories"}
    for name, rule in rules.items():
        assert rule and set(rule) <= allowed, name
        for keys in rule.values():
            assert all(isinstance(k, str) and k for k in keys), name
