#!/bin/sh
if [ $(bluetoothctl show | grep "Powered: yes" | wc -c) -eq 0 ]
then
  echo "%{F#66ffffff}"
else
  num_connected=$(bluetoothctl devices Connected | wc -l)
  if [ $num_connected -eq 0 ]
  then 
    echo " 0"
  fi
  echo "%{F#2193ff} ${num_connected}"
fi
