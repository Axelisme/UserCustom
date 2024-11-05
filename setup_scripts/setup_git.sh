#!/usr/bin/env bash
set -e

read -p 'Username: ' uservar
read -p 'Email: ' emailvar

git config --global user.name "$uservar"
git config --global user.email "$emailvar"

