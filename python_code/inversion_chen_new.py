# -*- coding: utf-8 -*-
"""Script for performing FFM modelling and forward, using the method of
Chen-Ji.
"""


import os
import json
import logging
import subprocess
from shutil import copy2
import glob
from data_acquisition import acquisition
import velocity_models as mv
import seismic_tensor as tensor
import data_processing as proc
import plot_graphic as plot
import input_files
import time
import management as mng
import plane_management as pl_mng
from load_ffm_model import load_ffm_model
import data_management as dm
import traces_properties as tp
import modulo_logs as ml
import green_functions as gf
import fault_plane as pf
import modelling_parameters as mp
from multiprocessing import Process
from static2fsp import static_to_fsp
import numpy as np
import errno
import get_outputs


def automatic_usgs(tensor_info, data_type, default_dirs, velmodel=None,
                   dt_cgps=1.0):
    """Routine for automatic FFM modelling
    
    :param tensor_info: dictionary with moment tensor properties
    :param data_type: list with data types to be used in modelling
    :param default_dirs: dictionary with default directories to be used
    :param velmodel: dictionary with velocity model
    :param dt_cgps: sampling interval for cgps data 
    :type tensor_info: dict
    :type data_type: list
    :type default_dirs: dict
    :type velmodel: dict, optional
    :type dt_cgps: float, optional
    """
    logger = ml.create_log('automatic_ffm',
                os.path.join('logs', 'automatic_ffm.log'))    
    logger.info('Starting fff program')
    sol_folder = os.getcwd()
    sol_folder = os.path.abspath(sol_folder)
    time0 = time.time()
    data_prop = tp.properties_json(tensor_info, dt_cgps=dt_cgps)
    os.chdir(os.path.join(sol_folder, 'data'))
    time2 = time.time()
    logger.info('Process data')
    processing(tensor_info, data_type, data_prop)
    time2 = time.time() - time2
    print('Time spent processing traces: \n', time2)
    os.chdir(sol_folder)
    muestreo = data_prop['sampling']
    dt_str = muestreo['dt_strong']
    logger.info('Compute GF bank')
    if not velmodel:
        velmodel = mv.select_velmodel(tensor_info, default_dirs)
    input_files.write_velmodel(velmodel)
    gf_bank_str = os.path.join(sol_folder, 'GF_strong')
    gf_bank_cgps = os.path.join(sol_folder, 'GF_cgps')
    get_gf_bank = default_dirs['strong_motion_gf_bank2']
    if 'cgps' in data_type:
        green_dict = gf.fk_green_fun1(dt_cgps, tensor_info, gf_bank_cgps, cgps=True)
        input_files.write_green_file(green_dict, cgps=True)
        with open(os.path.join('logs', 'GF_cgps_log'), "w") as out_gf_cgps:
            p1 = subprocess.Popen([get_gf_bank, 'cgps'], stdout=out_gf_cgps)
        p1.wait()
    if 'strong_motion' in data_type:
        green_dict = gf.fk_green_fun1(dt_str, tensor_info, gf_bank_str)
        input_files.write_green_file(green_dict)
        with open(os.path.join('logs', 'GF_strong_log'), "w") as out_gf_strong:
            p2 = subprocess.Popen([get_gf_bank, ], stdout=out_gf_strong)
        p2.wait()
    
    files = [
            'Green.in',
            'Green_cgps.in',
            'modelling_stats.json',
            os.path.join('data', 'gps_data'),
            'strong_motion_gf.json',
            'cgps_gf.json',
            'sampling_filter.json'
    ]
    folders = ['NP1', 'NP2']
    for folder in folders:
        for file in files:
            if os.path.isfile(file):
                copy2(file, folder)
    info_np1, info_np2 = tensor.planes_from_tensor(tensor_info)
    keywords = {'velmodel': velmodel}
    os.chdir(os.path.join(sol_folder, 'NP1'))
    p1 = Process(target=_automatic2,
                 args=(tensor_info, info_np1, data_type, data_prop, default_dirs),
                 kwargs=keywords)
    p1.start()
    os.chdir(os.path.join(sol_folder, 'NP2'))
    p2 = Process(target=_automatic2,
                 args=(tensor_info, info_np2, data_type, data_prop, default_dirs),
                 kwargs=keywords)
    p2.start()
    [p.join() for p in [p1, p2]]
    print('Time spent: ', time.time() - time0)
    ml.close_log(__name__)
    return


def _automatic2(tensor_info, plane_data, data_type, data_prop, default_dirs,
               velmodel=None):
    """Routine for automatic FFM modelling for each nodal plane
    
    :param tensor_info: dictionary with moment tensor properties
    :param plane_data: dictionary with fault plane mechanism
    :param data_type: list with data types to be used in modelling
    :param default_dirs: dictionary with default directories to be used
    :param data_prop: dictionary with properties for different waveform types
    :param velmodel: dictionary with velocity model
    :type default_dirs: dict
    :type tensor_info: dict
    :type plane_data: dict
    :type data_type: list
    :type data_prop: dict
    :type velmodel: dict, optional
    """
    logger = logging.getLogger('automatic_ffm')
#
# Create JSON files
#
    logger.info('Create automatic JSON')
    tensor.write_tensor(tensor_info)
    if velmodel:
        mv.velmodel2json(velmodel)
    if not velmodel:
        velmodel = mv.select_velmodel(tensor_info, default_dirs)
    np_plane_info = plane_data['plane_info']
    data_folder = os.path.join('..', 'data')
    dm.filling_data_dicts(tensor_info, data_type, data_prop, data_folder)
    pf.create_finite_fault(tensor_info, np_plane_info, data_type)
    mp.modelling_prop(tensor_info, data_type=data_type)
#
# write text files from JSONs
#
    segments, rise_time = pl_mng.__get_planes_json()
    rupt_vel = segments[0]['rupture_vel']
    lambda_min = 0.5
    lambda_max = 1.25
#    if {'gps', 'cgps', 'strong_motion'} & set(data_type):
#        lambda_min = 0.6
#        lambda_max = 1.2
#    if tensor_info['moment_mag'] < 8 * 10**25: 
#        lambda_min, lambda_max = [1, 1]
    min_vel, max_vel = [lambda_min * rupt_vel, lambda_max * rupt_vel]
    logger.info('Write input files')
    writing_inputs(tensor_info, data_type, min_vel, max_vel)
#
# Modelling and plotting results
#
    inversion(tensor_info, data_type, default_dirs, 'automatic_ffm')
    logger.info('Plot data in folder {}'.format(os.getcwd()))
    execute_plot(tensor_info, data_type, default_dirs)
    base = os.path.basename(os.getcwd())
    dirname = os.path.abspath(os.getcwd())
#
# write solution in FSP format
#
    segments_data, rise_time, point_sources = pl_mng.__read_planes_info()
    solution = get_outputs.read_solution_static_format(segments)
    static_to_fsp(tensor_info, segments_data, rise_time, point_sources,
                  data_type, velmodel, solution)
    for file in glob.glob('*png'):
        if os.path.isfile(os.path.join(dirname, base, file)):
            copy2(os.path.join(dirname, base, file),
                  os.path.join(dirname, 'plots'))
    


def manual_modelling(tensor_info, data_type, default_dirs):
    """Routine for manual finite fault modelling.
    
    :param tensor_info: dictionary with moment tensor properties
    :param data_type: list with data types to be used in modelling
    :param default_dirs: dictionary with default directories to be used
    :type default_dirs: dict
    :type tensor_info: dict
    :type data_type: list
    """
    if not os.path.isdir('logs'):
        os.mkdir('logs')
    if not os.path.isdir('plots'):
        os.mkdir('plots')
    min_vel, max_vel = __ask_velrange()
    logger = ml.create_log(
                'manual_ffm', os.path.join('logs', 'manual_ffm.log'))
    logger.info('Write input files')
    tensor.write_tensor(tensor_info)
    writing_inputs(tensor_info, data_type, min_vel, max_vel)
    inversion(tensor_info, data_type, default_dirs, 'manual_ffm')
    logger.info('Plot data in folder {}'.format(os.getcwd()))
    execute_plot(tensor_info, data_type, default_dirs)


def forward_modelling(tensor_info, default_dirs, data_type={'tele_body'},
                      option='Solucion.txt', max_slip=200):
    """Routine for forward modelling.
    
    :param tensor_info: dictionary with moment tensor properties
    :param data_type: set with data types to be used in modelling
    :param option: string with location of input file with kinematic model to
     use
    :param max_slip: maximum slip in case of checkerboard test
    :param default_dirs: dictionary with default directories to be used
    :type default_dirs: dict
    :type tensor_info: dict
    :type data_type: set, optional
    :type option: string, optional
    :type max_slip: float, optional
    """
    tensor.write_tensor(tensor_info)
    if not os.path.isdir('logs'):
        os.mkdir('logs')
    if not os.path.isdir('plots'):
        os.mkdir('plots')
    len_stk = 5 if not option == 'point_source' else 8
    len_dip = 5 if not option == 'point_source' else 1
#
# Get input model
#
    model = load_ffm_model(
            option=option, max_slip=max_slip, len_stk=len_stk, len_dip=len_dip)
    if not os.path.isfile('velmodel_data.json'):
        raise FileNotFoundError(
                errno.ENOENT, os.strerror(errno.ENOENT), 'velmodel_data.json')
    velmodel = json.load(open('velmodel_data.json'))
    min_vel, max_vel = __ask_velrange()

    logger = ml.create_log('forward_model',
                os.path.join('logs', 'forward_model.log'))
    logger.info('Write input files')
    segments_data, rise_time, point_sources = pl_mng.__read_planes_info()
    shear = pf.shear_modulous(point_sources, velmodel=velmodel)
    dx = segments_data[0]['delta_x']
    dy = segments_data[0]['delta_y']
    slip = model['slip']
    zipped = zip(slip, shear)
    moment_sub = [dx * dy * slip_seg * shear_seg\
                  for slip_seg, shear_seg in zipped]
    moment = np.sum(
            [np.sum(moment_seg.flatten()) for moment_seg in moment_sub])
    moment = 10**10 * moment
    writing_inputs(tensor_info, data_type, min_vel, max_vel, moment_mag=moment,
                   forward_model=model)
    inversion(tensor_info, data_type, default_dirs, 'forward_model',
              forward=True)
    logger.info('Plot data in folder {}'.format(os.getcwd()))
    execute_plot(tensor_info, data_type, default_dirs)


def checkerboard(tensor_info, data_type, default_dirs, max_slip=200,
                 add_error=False, option='Checkerboard',
                 option2='FFM modelling'):
    """Routine for running checkerboard tests.
    
    :param tensor_info: dictionary with moment tensor properties
    :param data_type: set with data types to be used in modelling
    :param option: string with location of input file with kinematic model to
     use
    :param max_slip: maximum slip in case of checkerboard test
    :param add_error: whether we add noise to synthetic waveforms
    :param option2: whether we invert the checkerboard model or not
    :param default_dirs: dictionary with default directories to be used
    :type default_dirs: dict
    :type tensor_info: dict
    :type data_type: set
    :type option: string, optional
    :type max_slip: float, optional
    :type add_error: bool, optional
    :type option2: string, optional
    """
    if max_slip > 0:
        folder_name = 'checkerboard_resolution'
    else:
        folder_name = 'checkerboard_noise'
    if not option == 'Checkerboard':
        folder_name = option
    if not os.path.isdir(folder_name):
        os.mkdir(folder_name)
    if not os.path.isdir('logs'):
        os.mkdir('logs')
    if not os.path.isdir('plots'):
        os.mkdir('plots')
    for file in os.listdir():
        if os.path.isfile(file):
            copy2(file, folder_name)
    os.chdir(folder_name)
    forward_modelling(tensor_info, default_dirs, data_type=data_type,
                      option=option, max_slip=max_slip)
    for data_type0 in data_type:
        if data_type0 == 'tele_body':
            json_dict = 'tele_waves.json'
        if data_type0 == 'surf_tele':
            json_dict = 'surf_waves.json'
        if data_type0 == 'strong_motion':
            json_dict = 'strong_motion_waves.json'
        if data_type0 == 'cgps':
            json_dict = 'cgps_waves.json'
        if data_type0 == 'gps':
            json_dict = 'static_data.json'
        if data_type0 == 'dart':
            json_dict = 'dart_waves.json'
        files = json.load(open(json_dict))
        input_files.from_synthetic_to_obs(
                files, data_type0, tensor_info, add_error=add_error)
    logger = ml.create_log('checkerboard_ffm',
                           os.path.join('logs', 'checkerboard_ffm.log'))
    if option2 == 'FFM modelling':
        inversion(tensor_info, data_type, default_dirs, 'checkerboard_ffm')
        execute_plot(tensor_info, data_type, default_dirs, plot_input=True)
    
    
def set_directory_structure(tensor_info):
    """Create directory structure
    
    :param tensor_info: dictionary with moment tensor properties
    :type tensor_info: dict
    """
    sol_folder = mng.start_time_id(tensor_info)
    if not os.path.isdir(sol_folder):
        os.mkdir(sol_folder)
    sol_folder = os.path.abspath(sol_folder)
    version = len(glob.glob(os.path.join(sol_folder, 'pk*')))
    sol_folder2 = os.path.join(sol_folder, 'pk.{}'.format(version))
    os.mkdir(sol_folder2)
    os.mkdir(os.path.join(sol_folder2, 'data'))
    os.mkdir(os.path.join(sol_folder2, 'data', 'cGPS'))
    os.mkdir(os.path.join(sol_folder2, 'data', 'STR'))
    os.mkdir(os.path.join(sol_folder2, 'data', 'P'))
    os.mkdir(os.path.join(sol_folder2, 'data', 'SH'))
    os.mkdir(os.path.join(sol_folder2, 'data', 'LONG'))
    os.mkdir(os.path.join(sol_folder2, 'data', 'final'))
    os.mkdir(os.path.join(sol_folder2, 'data', 'final_r'))
    os.mkdir(os.path.join(sol_folder2, 'NP1'))
    os.mkdir(os.path.join(sol_folder2, 'NP1', 'logs'))
    os.mkdir(os.path.join(sol_folder2, 'NP1', 'plots'))
    os.mkdir(os.path.join(sol_folder2, 'NP2'))
    os.mkdir(os.path.join(sol_folder2, 'NP2', 'logs'))
    os.mkdir(os.path.join(sol_folder2, 'NP2', 'plots'))
    os.mkdir(os.path.join(sol_folder2, 'logs'))
    os.mkdir(os.path.join(sol_folder2, 'plots'))
    os.mkdir(os.path.join(sol_folder2, 'plots', 'NP1'))
    os.mkdir(os.path.join(sol_folder2, 'plots', 'NP2'))
    os.chdir(sol_folder2)
    return


def adquisicion(tensor_info):
    """Get waveforms and convert them to SAC using obspy.
    """
    event_time = tensor_info['date_origin']
    event_lat = tensor_info['lat']
    event_lon = tensor_info['lon']
    depth = tensor_info['depth']
    data_type = ['tele']
    if -50 < event_lat < -18 and -75 < event_lon < -60\
    and event_time.year >= 2014:
        data_type = data_type + ['strong']
    acquisition(event_time, event_lat, event_lon, depth, data_type)
    
    
def processing(tensor_info, data_type, data_prop):
    """Run all waveform data processing in parallel.
    
    :param tensor_info: dictionary with moment tensor properties
    :param data_type: set with data types to be used in modelling
    :param data_prop: dictionary with properties for different waveform types
    :type tensor_info: dict
    :type data_type: set
    :type data_prop: dict
    """
    #print(data_type)
    #print(os.getcwd())
    tele_files = glob.glob('*.BH*SAC') + glob.glob('*.BH*sac') + glob.glob('*_BH*sac') + glob.glob('*_BH*SAC')
    strong_files = glob.glob('*.HN*SAC') + glob.glob('*.HL*SAC')\
                   + glob.glob('*.HN*sac') + glob.glob('*.HL*sac')
#    cgps_files = glob.glob('*.L[HX]*SAC') + glob.glob('*.L[HX]*sac')
    cgps_files = glob.glob('*LY*sac')
    p1 = Process(target=proc.select_process_tele_body,
                 args=(tele_files, tensor_info, data_prop))
    p2 = Process(target=proc.select_process_surf_tele,
                 args=(tele_files, tensor_info))
    p3 = Process(target=proc.select_process_strong,
                 args=(strong_files, tensor_info, data_prop))
    p4 = Process(target=proc.select_process_cgps,
                 args=(cgps_files, tensor_info, data_prop))
    processes = []
    processes = processes + [p1] if 'tele_body' in data_type\
        else processes
    processes = processes + [p2] if 'surf_tele' in data_type\
        else processes
    processes = processes + [p3] if 'strong_motion' in data_type\
        else processes
    processes = processes + [p4] if 'cgps' in data_type else processes
    [p.start() for p in processes]
    [p.join() for p in processes]
    del processes


def writing_inputs(tensor_info, data_type, min_vel, max_vel, moment_mag=None,
                   forward_model=None):
    """Write all required text files from the information found in the JSONs.
    
    :param tensor_info: dictionary with moment tensor properties
    :param data_type: set with data types to be used in modelling
    :param min_vel: minimum rupture velocity
    :param max_vel: maximum rupture velocity
    :param moment_mag: input seismic moment
    :param forward_model: input kinematic model
    :type tensor_info: dict
    :type data_type: set
    :type min_vel: float
    :type max_vel: float
    :type moment_mag: float, optional
    :type forward_model: dict, optional
    """
    if not os.path.isfile('velmodel_data.json'):
        raise FileNotFoundError(
                errno.ENOENT, os.strerror(errno.ENOENT), 'velmodel_data.json')
    velmodel = json.load(open('velmodel_data.json'))
    input_files.write_velmodel(velmodel)
    segments, rise_time = pl_mng.__get_planes_json()
    input_files.plane_for_chen(tensor_info, segments, rise_time,
                               min_vel, max_vel, velmodel)
    if forward_model:
        input_files.forward_model(tensor_info, segments, rise_time,
                                  forward_model, min_vel, max_vel)
    if not os.path.isfile('sampling_filter.json'):
        raise FileNotFoundError(
                errno.ENOENT, os.strerror(errno.ENOENT), 'sampling_filter.json')
    data_prop = json.load(open('sampling_filter.json'))
    if 'tele_body' in data_type:            
        input_files.input_chen_tele_body(tensor_info, data_prop)
    if 'surf_tele' in data_type:
        input_files.input_chen_tele_surf(tensor_info, data_prop)
    if 'strong_motion' in data_type:
        input_files.input_chen_strong_motion(tensor_info, data_prop)
    if 'cgps' in data_type:
        input_files.input_chen_cgps(tensor_info, data_prop)
    if 'gps' in data_type:
        input_files.input_chen_static(tensor_info)
    if 'dart' in data_type:
        input_files.input_chen_dart(tensor_info, data_prop)
    if not os.path.isfile('annealing_prop.json'):
        raise FileNotFoundError(
                errno.ENOENT, os.strerror(errno.ENOENT), 'annealing_prop.json')
    dictionary = json.load(open('annealing_prop.json'))
    if moment_mag:
        dictionary['seismic_moment'] = moment_mag
    input_files.inputs_simmulated_annealing(dictionary, data_type)
    if 'cgps' in data_type:
        if not os.path.isfile('cgps_gf.json'):
            raise FileNotFoundError(
                    errno.ENOENT, os.strerror(errno.ENOENT), 'cgps_gf.json')
        green_dict = json.load(open('cgps_gf.json'))
        input_files.write_green_file(green_dict, cgps=True)
    if 'strong_motion' in data_type:
        if not os.path.isfile('strong_motion_gf.json'):
            raise FileNotFoundError(
                    errno.ENOENT, os.strerror(errno.ENOENT), 'strong_motion_gf.json')
        green_dict = json.load(open('strong_motion_gf.json'))
        input_files.write_green_file(green_dict)
    if not os.path.isfile('model_space.json'):
        raise FileNotFoundError(
                errno.ENOENT, os.strerror(errno.ENOENT), 'model_space.json')
    segments2 =json.load(open('model_space.json'))
    input_files.model_space(segments2, rise_time)
    return


def inversion(tensor_info, data_type, default_dirs, name_log, forward=False):
    """We get the binaries with gf for each station, run the ffm code, and
    proceed to plot the results.
    
    :param tensor_info: dictionary with moment tensor properties
    :param data_type: set with data types to be used in modelling
    :param name_log: name of logfile to write
    :param forward: whether we solve the inverse problem or the forward problem
    :param default_dirs: dictionary with default directories to be used
    :type default_dirs: dict
    :type tensor_info: dict
    :type data_type: set
    :type data_prop: string
    :type forward: bool, optional
    """
    print('data_type: ', data_type)
    logger = logging.getLogger(name_log)
    logger.info('Green_functions')
    time1 = time.time()
    gf.gf_retrieve(data_type, default_dirs)
    time1 = time.time() - time1
    run_stats = dict()
    run_stats['gf_time'] = time1
    print('Elapsed time of green_fun: {}'.format(time1))
    time3 = time.time()
    args = ['auto']
    args = args + ['strong'] if 'strong_motion' in data_type else args
    args = args + ['cgps'] if 'cgps' in data_type else args
    args = args + ['body'] if 'tele_body' in data_type else args
    args = args + ['surf'] if 'surf_tele' in data_type else args
    args = args + ['gps'] if 'gps' in data_type else args
    args = args + ['dart'] if 'dart' in data_type else args
    if not forward:
        logger.info('Inversion at folder {}'.format(os.getcwd()))
        finite_fault = default_dirs['finite_fault']
    else:
        logger.info('Forward at folder {}'.format(os.getcwd()))
        finite_fault = default_dirs['forward']
    p1 = subprocess.Popen([finite_fault, *args])
#
# need to wait until FFM modelling is finished.
#
    p1.wait()
    time3 = time.time() - time3
    print('Elapsed time of finite fault modelling: {}'.format(time3))
    run_stats['ffm_time'] = time3
    delete_binaries()
    return run_stats


def execute_plot(tensor_info, data_type, default_dirs, velmodel=None,
                 plot_input=False):
    """We plot modelling results
    
    :param tensor_info: dictionary with moment tensor properties
    :param data_type: set with data types to be used in modelling
    :param plot_input: choose whether to plot initial kinematic model as well
    :param default_dirs: dictionary with default directories to be used
    :param velmodel: dictionary with velocity model
    :type velmodel: dict, optional
    :type default_dirs: dict
    :type tensor_info: dict
    :type data_type: set
    :type plot_input: bool, optional
    """
    segments, rise_time, point_sources = pl_mng.__read_planes_info()
    solution = get_outputs.read_solution_static_format(segments)
    if not velmodel:
        velmodel = mv.select_velmodel(tensor_info, default_dirs)
    shear = pf.shear_modulous(point_sources)
    plot.plot_ffm_sol(tensor_info, segments, point_sources, shear, solution,
                      velmodel, default_dirs)
    plot.plot_misfit(data_type)
    traces_info, stations_gps = [None, None]
    if 'strong_motion' in data_type:
        traces_info = json.load(open('strong_motion_waves.json'))
    if 'gps' in data_type:
        names, lats, lons, observed, synthetic, error = get_outputs.retrieve_gps()
        stations_gps = zip(names, lats, lons, observed, synthetic, error)
    if 'strong_motion' in data_type or 'gps' in data_type:
        plot._PlotMap(tensor_info, segments, point_sources, solution,
                      default_dirs, files_str=traces_info,
                      stations_gps=stations_gps)
    if plot_input:
        input_model = load_ffm_model(option='Fault.time')
        plot._PlotSlipDist_Compare(tensor_info, segments, point_sources,
                                   input_model, solution)
        plot._PlotComparisonMap(tensor_info, segments, point_sources,
                                input_model, solution)
    

def delete_binaries():
    """to remove the files with Green function data.
    """
    deletables = glob.glob('*.GRE') + glob.glob('*.TDE') + glob.glob('*[1-2-3]')
    for file in deletables:
        if os.path.isfile(file):
            os.remove(file)


def __ask_velrange():
    min_vel = float(input('Minimum rupture velocity: '))
    max_vel = float(input('Maximum rupture velocity: '))
    return min_vel, max_vel
            
            
if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--folder", default=os.getcwd(),
                        help="folder where there are input files")
    parser.add_argument("-gcmt", "--gcmt_tensor",
                        help="location of GCMT moment tensor file")
    parser.add_argument("-o", "--option",
                        choices=[
                                'auto',
                                'manual',
                                'forward',
                                'point_source',
                                'checker_mod',
                                'checker_noise',
                                'point_source_err',
                                'forward_patch'
                        ],
                        required=True, help="which method to run")
    parser.add_argument("-d", "--data",
                        help="direction of folder with seismic data")
    parser.add_argument("-v", "--velmodel", 
                        help="direction of velocity model file")
    parser.add_argument("-i", "--iris", action="store_true",
                        help="whether data has been retrieved from iris")
    parser.add_argument("-t", "--tele", action="store_true",
                        help="use teleseismic data in modelling")
    parser.add_argument("-su", "--surface", action="store_true",
                        help="use surface waves data in modelling")
    parser.add_argument("-st", "--strong", action="store_true",
                        help="use strong motion data in modelling")
    parser.add_argument("--cgps", action="store_true",
                        help="use cGPS data in modelling")
    parser.add_argument("--gps", action="store_true",
                        help="use GPS data in modelling")
    args = parser.parse_args()
    velmodel = args.velmodel if args.velmodel else None
    if velmodel:
        velmodel = mv.model2dict(velmodel)
    os.chdir(args.folder)
    data_type = []
    data_type = data_type + ['gps'] if args.gps else data_type
    data_type = data_type + ['strong_motion'] if args.strong else data_type
    data_type = data_type + ['cgps'] if args.cgps else data_type
    data_type = data_type + ['tele_body'] if args.tele else data_type
    data_type = data_type + ['surf_tele'] if args.surface else data_type
  
    default_dirs = mng.default_dirs()
#    if args.option == 'auto':
#        if not args.gcmt_tensor:
#            raise RuntimeError('You must select direction of input GCMT file')
#        tensor_info = tensor.get_tensor(cmt_file=args.gcmt_tensor)
#        set_directory_structure(tensor_info)
#        if args.data:
#            for file in os.listdir(args.data):
#                if os.path.isfile(os.path.join(args.data, file)):
#                    copy2(os.path.join(args.data, file), 'data')
#        data_type = data_type if len(data_type) >= 1 else ['tele_body']
#        get_data = 'obspy' if not args.iris else 'IRIS'
#        automatic(tensor_info, default_dirs, data_type, velmodel=velmodel,
#                  get_data=get_data)
    if args.option == 'auto':
        if not args.gcmt_tensor:
            raise RuntimeError('You must select direction of input GCMT file')
        tensor_info = tensor.get_tensor(cmt_file=args.gcmt_tensor)
        set_directory_structure(tensor_info)
        if args.data:
            for file in os.listdir(args.data):
                if os.path.isfile(os.path.join(args.data, file)):
                    copy2(os.path.join(args.data, file), 'data')
        data_type = data_type if len(data_type) >= 1 else ['tele_body']
        automatic_usgs(tensor_info, data_type, default_dirs, velmodel=velmodel,
                       dt_cgps=0.2)
    if args.option == 'manual':
        if args.gcmt_tensor:
            cmt_file = args.gcmt_tensor
            tensor_info = tensor.get_tensor(cmt_file=cmt_file)
        else:
            tensor_info = tensor.get_tensor()
        if len(data_type) == 0:
            raise RuntimeError('You must input at least one data type')
        data_folder = args.data if args.data else None
        manual_modelling(tensor_info, data_type, default_dirs)#, data_folder=data_folder)
    if args.option == 'forward':
        if args.gcmt_tensor:
            cmt_file = args.gcmt_tensor
            tensor_info = tensor.get_tensor(cmt_file=cmt_file)
        else:
            tensor_info = tensor.get_tensor()
        if len(data_type) == 0:
            raise RuntimeError('You must input at least one data type')
        data_folder = args.data if args.data else None
        forward_modelling(tensor_info, data_type, default_dirs,
                          option='Solucion.txt')
    if args.option == 'forward_patch':
        if args.gcmt_tensor:
            cmt_file = args.gcmt_tensor
            tensor_info = tensor.get_tensor(cmt_file=cmt_file)
        else:
            tensor_info = tensor.get_tensor()
        if len(data_type) == 0:
            raise RuntimeError('You must input at least one data type')
        data_folder = args.data if args.data else None
        checkerboard(tensor_info, data_type, default_dirs, max_slip=400,
                     option='Patches', option2='forward')
    if args.option == 'checker_mod':
        if args.gcmt_tensor:
            cmt_file = args.gcmt_tensor
            tensor_info = tensor.get_tensor(cmt_file=cmt_file)
        else:
            tensor_info = tensor.get_tensor()
        if len(data_type) == 0:
            raise RuntimeError('You must input at least one data type')
        data_folder = args.data if args.data else None
        checkerboard(tensor_info, data_type, default_dirs)
    if args.option == 'checker_noise':
        if args.gcmt_tensor:
            cmt_file = args.gcmt_tensor
            tensor_info = tensor.get_tensor(cmt_file=cmt_file)
        else:
            tensor_info = tensor.get_tensor()
        if len(data_type) == 0:
            raise RuntimeError('You must input at least one data type')
        data_folder = args.data if args.data else None
        checkerboard(tensor_info, data_type, default_dirs, max_slip=0,
                     add_error=True)
    if args.option == 'point_source':
        if args.gcmt_tensor:
            cmt_file = args.gcmt_tensor
            tensor_info = tensor.get_tensor(cmt_file=cmt_file)
        else:
            tensor_info = tensor.get_tensor()
        if len(data_type) == 0:
            raise RuntimeError('You must input at least one data type')
        data_folder = args.data if args.data else None
        checkerboard(tensor_info, data_type, default_dirs, max_slip=500,
                     option='Patches')
    if args.option == 'point_source_err':
        if args.gcmt_tensor:
            cmt_file = args.gcmt_tensor
            tensor_info = tensor.get_tensor(cmt_file=cmt_file)
        else:
            tensor_info = tensor.get_tensor()
        if len(data_type) == 0:
            raise RuntimeError('You must input at least one data type')
        data_folder = args.data if args.data else None
        checkerboard(tensor_info, data_type, default_dirs, max_slip=300,
                     option='Patches', add_error=True)
