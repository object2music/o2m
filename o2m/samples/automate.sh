#!/bin/bash
hour=$(date +%H)
day=$(date +%u)

#Week mornings
if [ "$hour" -ge 6 ] && [ "$hour" -lt 9 ]  && [ "$day" -ge 1 ]  && [ "$day" -lt 5 ]; then
    wget http://pi.local:6681/api/box?uid=auto_podcast:library&mode=add
fi
#Weekend mornings
if [ "$hour" -ge 6 ] && [ "$hour" -lt 9 ]  && [ "$day" -ge 5 ]; then
    wget http://pi.local:6681/api/box?uid=04AD43D2204B80&mode=add
fi
