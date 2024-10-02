#!/usr/bin/env bash

read -p 'Username: ' uservar
read -p 'Email: ' emailvar

git config --global user.name   "$uservar" ;
git config --global user.email  "$emailvar" ;
git config --global url.ssh://git@github.com/.insteadOf https://github.com/;