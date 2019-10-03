
import numpy as np

from . import input_data_dir
from .leaf_angle_dist import ( G_ellipsoidal_approx, 
    mean_leaf_angle_to_orient, )
from .leaf_area_alloc import ( distribute_lai_from_cdd, 
    distribute_lai_beta )
# from .utils import ( load_canopy_descrip, load_default_leaf_soil_props, 
#     load_default_toc_spectra )


def load_canopy_descrip(fname):
    """Load items from CSV file and return as dict
    The file should use the same fieldnames as in the default one!
    Pandas might also do this.
    """
    varnames, vals = np.genfromtxt(fname, 
                                   usecols=(0, 1), skip_header=1, delimiter=',',  
                                   dtype=str, unpack=True)
    
    n = varnames.size
    d_raw = {varnames[i]: vals[i] for i in range(n)}
#    print d_raw
    
    d = d_raw  # could copy instead
    for k, v in d.items():
        if ';' in v:            
            d[k] = [float(x) for x in v.split(';')]
        else:
            d[k] = float(v)
#    print d
    
    #> checks
    assert( np.array(d['lai_frac']).sum() == 1.0 )
 
    return d
    


def load_default_leaf_soil_props():
    """
    Returns
    -------
    

    """

    # ----------------------------------------------------------------------------------------------
    # green leaf properties (alread at SPCTRAL2 wavelengths)

    leaf_data_file = '{data:s}/ideal-green-leaf/leaf-idealized-rad_SPCTRAL2_wavelengths_extended.csv'.format(data=input_data_dir)
    leaf_data = np.loadtxt(leaf_data_file,
                           delimiter=',', skiprows=1)
    wl  = leaf_data[:,0]  # all SPCTRAL2 wavelengths (to 4 um); assume band center (though may be left...)
    dwl = np.append(np.diff(wl), np.nan)  # um; UV region more important so add nan to end instead of beginning, though doesn't really matter since outside leaf data bounds

#    wl_a = 0.35  # lower limit of leaf data; um
    wl_a = 0.30  # lower limit of leaf data, extended; um
    wl_b = 2.6   # upper limit of leaf data; um
    leaf_data_wls = (wl >= wl_a) & (wl <= wl_b)

    # use only the region where we have leaf data
    #  initially, everything should be at the SPCTRAL2 wls
    wl    = wl[leaf_data_wls]
    dwl   = dwl[leaf_data_wls]

    leaf_t = leaf_data[:,1][leaf_data_wls]
    leaf_r = leaf_data[:,2][leaf_data_wls]

    leaf_t[leaf_t == 0] = 1e-10
    leaf_r[leaf_r == 0] = 1e-10

    # also eliminate < 0 values ??
    #   this was added to the leaf optical props generation
    #   but still having problem with some values == 0


    # ----------------------------------------------------------------------------------------------
    # soil reflectivity (assume these for now (used in Fuentes 2007)

    # soil_r = np.ones_like(wl)
    soil_r = np.ones(wl.shape)  # < please pylint
    soil_r[wl <= 0.7] = 0.1100  # this is the PAR value
    soil_r[wl > 0.7]  = 0.2250  # near-IR value

    return wl, dwl, leaf_r, leaf_t, soil_r



def load_default_toc_spectra():
    """Load sample top-of-canopy spectra (direct and diffuse).

    The irradiances are in spectral form: W m^-2 um^-1
    """

    fp = '{data:s}/sample_pyspctral2.csv'.format(data=input_data_dir)

    wl, dwl, I_dr0, I_df0 = np.loadtxt(fp, delimiter=',', unpack=True)

    wl_a = 0.30  # lower limit of leaf data, extended; um
    wl_b = 2.6   # upper limit of leaf data; um
    leaf_data_wls = (wl >= wl_a) & (wl <= wl_b)

    # use only the region where we have leaf data
    wl    = wl[leaf_data_wls]
    dwl   = dwl[leaf_data_wls]
    SI_dr0 = I_dr0[leaf_data_wls] #[np.newaxis,:]  # expects multiple cases
    SI_df0 = I_df0[leaf_data_wls] #[np.newaxis,:]

    return wl, dwl, SI_dr0*dwl, SI_df0*dwl




cnpy_descrip_keys = [\
    'lai', 'z', 'dlai', 'lai_tot', 'lai_eff', 
    'mean_leaf_angle', 
    'green', 
    'leaf_t', 
    'leaf_r',
    'soil_r',
    'wl_leafsoil', 
    'orient',  # don't really need both this and mla as input
    'G_fn',
    'K_b_fn', 
    ]

cnpy_rad_state_input_keys = [\
    'I_dr0', 'I_df0',  # spectral ()
    'wl', 'dwl',  # for the toc spectra
    'psi', 'mu',
    'K_b', 
    ]

cnpy_rad_state_keys = cnpy_rad_state_input_keys + [\
    'I_dr', 'I_df_d', 'I_df_u', 'F',  # direct from schemes
    'a_PAR', 'a_solar', 'a_UV', 'a_spectral',  # calculated (some schemes provide)
    'a_PAR_sl', 'a_PAR_sh', #... median wl for energy and photon perspective, photon flux, ...
    ]

def load_default_case(nlayers):
    """Idealized beta leaf dist, 

    """
    h_c = 20.
    LAI = 4.
    lai, z = distribute_lai_beta(h_c, LAI, nlayers)

    #> spectral things
    #  includes: top-of-canopy BC, leaf reflectivity and trans., soil refl, 
    #  for now, assume wavelengths from the BC apply to leaf as well
    wl_default, dwl_default, \
    leaf_r_default, leaf_t_default, \
    soil_r_default = load_default_leaf_soil_props()

    mla = 57  # for spherical? (check)
    orient = mean_leaf_angle_to_orient(mla)
    G_fn = lambda psi_: G_ellipsoidal_approx(psi_, orient)

    cnpy_descrip = dict(\
        lai=lai, z=z,
        green=1.0,
        mean_leaf_angle=mla,
        clump=1.0,
        leaf_t=leaf_t_default,
        leaf_r=leaf_r_default,
        soil_r=soil_r_default,
        wl_leafsoil=wl_default,
        orient=orient,
        G_fn=G_fn,
        )

    wl, dwl, I_dr0, I_df0 = load_default_toc_spectra()

    sza = 20  # deg.
    psi = np.deg2rad(sza)
    # mu = np.cos(psi)

    cnpy_rad_state = dict(\
        I_dr0_all=I_dr0, I_df0_all=I_df0, wl=wl, dwl=dwl, 
        psi=psi,
        )


    return cnpy_descrip, cnpy_rad_state








def load_Borden95_default_case(nlayers):
    """ """
    cdd_default = load_canopy_descrip(input_data_dir+'/'+'default_canopy_descrip.csv')
    lai, z = distribute_lai_from_cdd(cdd_default, nlayers)




# if __name__ == '__main__':

#     from .__init__ import input_data_dir 

#     cd, crs = load_default_case(10)
#     print(cd)
#     print(crs)
