@echo off

ffmpeg -y -i input.wav ^
-af "acompressor=threshold=-18dB:ratio=4:attack=20:release=200,equalizer=f=120:width_type=h:width=100:g=3" ^
temp.wav

sox temp.wav output.wav reverb 20 30 40 flanger 0.2 0.5 3 0.1 0.5

echo Processing complete.
pause