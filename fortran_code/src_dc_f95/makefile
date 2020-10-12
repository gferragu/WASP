##  If you want to change the size of GF bank, please just modify the size.h
FFLAGS=-O
MY_BIN=.
F77=gfortran -ffixed-line-length-132 -mcmodel=medium -O2 -Wall -mavx2 -g#-fbacktrace -ffpe-trap=underflow,denormal
# linux or Mac
#F77= ifort -132 -O2 -assume byterecl
#F77= gfortran -fno-rerun-loop-opt -fstrength-reduce -ffixed-line-length-132 -fno-range-check -mcmodel=large
#

modules = constants.o retrieve_gf.o bessel2.o vel_model_data.o wave_travel.o fk_source.o haskell.o prop.o fk_kernel.o fk.o bessel.o $(SUBS)
modules2 = constants.o retrieve_gf.o bessel2.o vel_model_data.o wave_travel.o layer.o fk_source.o haskell.o prop.o fk_kernel.o fk_openmp.o bessel.o $(SUBS)
modules3 = constants.o retrieve_gf.o bessel2.o vel_model_data.o wave_travel.o layer.o fk_source.o st_haskell.o prop.o fk_st_kernel.o fk_static.o bessel.o $(SUBS)
SUBS = fft.o Complex.o 
FKSUBS = green_bank_dc_3n.o cmodel_fk.o trav_fk.o fk_dc_4.o kernel.o prop.o haskell.o source.o bessel.o $(SUBS) # fk_dc_3.o
FKSUBS2 = green_bank_dc_31n.o cmodel_fk.o trav_fk.o fk_dc_41.o kernel.o prop.o haskell.o source.o bessel.o $(SUBS) # fk_dc_3.o
#FKSUBS_STA = gf_static.o ddis.o cmodel_fk.o trav_fk.o fk_dc_3.o kernel.o prop.o st_haskell.o source.o bessel.o $(SUBS) 
all: green_bank_openmp gf_static clean 


green_bank_fk: $(modules) green_bank_fk.o
	$(F77) -o $(MY_BIN)/green_bank_f95 $(modules) green_bank_fk.o

green_bank_openmp: $(modules2) green_bank_fk_openmp.o
	$(F77) -fopenmp -o $(MY_BIN)/green_bank_openmp_f95 $(modules2) green_bank_fk_openmp.o

gf_static: $(modules3) geodesics.o rad_pattern.o gf_static.o
	$(F77) -o $(MY_BIN)/gf_static_f95 $(modules3) geodesics.o rad_pattern.o gf_static.o


fk_openmp.mod: fk_openmp.o fk_openmp.f95
	$(F77) -fopenmp -c fk_openmp.f95

layer.mod: layer.o layer.f95
	$(F77) -fopenmp -c layer.f95

%.mod: %.o %.f95
	$(F77) -c $<


fft.o: fft.c 
	cc -c fft.c

Complex.o: Complex.c Complex.h
	cc -c Complex.c

bessel.o: bessel.f
	$(F77) -c bessel.f

bessel.f: bessel.FF
	cpp -traditional-cpp $< > $@

fk_openmp.o: fk_openmp.f95
	$(F77) -fopenmp -c fk_openmp.f95

layer.o: layer.f95
	$(F77) -fopenmp -c layer.f95

%.o: %.f95
	$(F77) -c $<

clean:
	rm -f *.mod
	rm -f *.o
