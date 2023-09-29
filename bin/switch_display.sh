#!/bin/bash
# This script is intended to make switching between laptop and external displays easier when using i3+dmenu 
# To run this script, map it to some shortcut in your i3 config, e.g:
# bindsym $mod+p exec --no-startup-id $config/display.sh
# IMPORTANT: run chmod +x on the script to make it executable
# The result is 4 options appearing in dmenu, from which you can choose


# This is your default laptop screen, detect by running `xrandr`
INTERNAL_OUTPUT="eDP-1"
EXTERNAL_OUTPUT="HDMI-1-0"

# choices will be displayed in dmenu
choices="inter_primary\nexter_primary\ninternal\nexternal\nauto"
# Your choice in dmenu will determine what xrandr command to run
chosen=$(echo -e $choices | rofi -dmenu -i -theme nord)

# xrander will run and turn on the display you want, if you have an option for 3 displays, this will need some modifications
case "$chosen" in
    inter_primary) xrandr --output $INTERNAL_OUTPUT --primary ;;
    exter_primary) xrandr --output $EXTERNAL_OUTPUT --primary ;;
    internal) xrandr --output $EXTERNAL_OUTPUT --off --output $INTERNAL_OUTPUT --auto --primary ;;
    external) xrandr --output $INTERNAL_OUTPUT --off --output $EXTERNAL_OUTPUT --auto --primary ;;
    auto) autorandr --change --skip-option crtc ;;
esac

sleep 0.4 && nitrogen --restore
