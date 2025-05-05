sudo rm -rf outputs

for ((i=1;i <= 100000; i+=100))
do
  sudo ./waf --run "scratch/bolt-dumb.cc $i"
  cd plot 
  python plot_fair.py $i
  cd ..
done
