BIN=./
OBJS3= fft.o mult_single.o interporation.o cmodel.o ddis.o  Read_green.o bpfilter.o
OBJS5= fft.o green_cgps.o interporation.o cmodel.o ddis.o  Read_green.o bpfilter.o
OBJS4= fft.o get_green_fun.o interporation.o cmodel.o ddis.o  Read_green.o bpfilter.o
modules = constants.o vel_model_data.o
modules2 = $(modules) geodesics.o retrieve_gf.o wave_travel.o bpfilter.o fast_fourier_trans.o rad_pattern.o
F95= gfortran -Wall -O2 -mavx2 -ffixed-line-length-132 -fno-range-check -mcmodel=medium -fbacktrace -g -fno-rerun-loop-opt

 
all: get_strong_motion clean


get_strong_motion: $(modules2) get_strong_motion.o
	$(F95) -o get_strong_motion $(modules2) get_strong_motion.o


%.mod: $.o $.f95
	$(f95) -c $<


%.o: %.f95
	$(F95) -c $<


clean:
	rm -f *.mod 
	rm -f *.o 
