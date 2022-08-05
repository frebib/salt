#!/bin/bash
#Need a login shell to use it
#TODO: update shell wrapper to use bash -l
PS1='\[\e[0;33m\][${SALT_MASTER_NAME}]\[\e[0m\] \u@\h: \w \$ '