from sympy import inverse_mellin_transform
import taichi as ti
import numpy as np
from pyevtk.hl import gridToVTK
import time

#ti.init(arch=ti.cpu, dynamic_index=False, kernel_profiler=False, print_ir=False)
import LBM_3D_SinglePhase_Solver as lb3d

@ti.data_oriented
class LB3D_Solver_Single_Phase_Solute(lb3d.LB3D_Solver_Single_Phase):
    def __init__(self, nx, ny, nz):
        super(LB3D_Solver_Single_Phase_Solute, self).__init__(nx, ny, nz, sparse_storage = False)

        self.solute_bc_x_left, self.solute_bcxl = 0, 0.0
        self.solute_bc_x_right, self.solute_bcxr = 0, 0.0
        self.solute_bc_y_left, self.solute_bcyl = 0, 0.0
        self.solute_bc_y_right, self.solute_bcyr = 0, 0.0
        self.solute_bc_z_left, self.solute_bczl = 0, 0.0
        self.solute_bc_z_right, self.solute_bczr = 0, 0.0

        #self.solute_diffusive_bc_x_left, self.diffusive_bcxl = 0, 0.0
        #self.solute_diffusive_bc_x_right, self.diffusive_bcxr = 0, 0.0
        #self.solute_diffusive_bc_y_left, self.diffusive_bcyl = 0, 0.0
        #self.solute_diffusive_bc_y_right, self.diffusive_bcyr = 0, 0.0
        #self.solute_diffusive_bc_z_left, self.diffusive_bczl = 0, 0.0
        #self.solute_diffusive_bc_z_right, self.diffusive_bczr = 0, 0.0

        self.buoyancy_parameter = 20.0   #Buoyancy Parameter (0= no buoyancy)
        self.ref_T = 20.0              #reference_psi F=/rho*g+Bouyancy*(/psi-reference_psi)*g)
        self.gravity = 5e-7
        
        self.fg = ti.Vector.field(19,ti.f32,shape=(nx,ny,nz))
        self.Fg = ti.Vector.field(19,ti.f32,shape=(nx,ny,nz))
        self.forcexyz = ti.Vector.field(3,ti.f32,shape=(nx,ny,nz))
        self.rho_H = ti.field(ti.f32, shape=(nx,ny,nz))
        self.rho_T = ti.field(ti.f32, shape=(nx,ny,nz))
        self.rho_fl = ti.field(ti.f32, shape=(nx,ny,nz))

        #self.Cp_l = self.ti.field(ti.f32, shape=())
        #self.Cp_s = self.ti.field(ti.f32, shape=())
        #self.niu_s = self.ti.field(ti.f32, shape=())
        #self.niu_l = self.ti.field(ti.f32, shape=())
        #self.Lt = self.ti.field(ti.f32, shape=())

        self.Cp_l= 1.0
        self.Cp_s = 1.0
        self.Lt = 1.0
        self.T_s = -10.0
        self.T_l = -10.0
        self.niu_s = 0.002
        self.niu_l = 0.002

        self.H_s = None
        self.H_l = None

        self.niu_solid = 0.001
        self.Cp_solid = 1.0
        

    def set_gravity(self, gravity):
        self.gravity = gravity

    def set_buoyancy_parameter(self, buoyancy_param):
        self.buoyancy_parameter = buoyancy_param
    
    def set_ref_T(self, ref_t):
        self.ref_T = ref_t

    def set_specific_heat_solid(self, cps):
        self.Cp_s = cps

    def set_specific_heat_liquid(self, cpl):
        self.Cp_l = cpl

    def set_specific_heat_rock(self, cprock):
        self.Cp_solid = cprock

    def set_latent_heat(self, ltheat):
        self.Lt = ltheat

    def set_solidus_temperature(self, ts):
        self.T_s = ts
    
    def set_liquidus_temperature(self, tl):
        self.T_l = tl
    
    def set_solid_thermal_diffusivity(self, nius):
        self.niu_s = nius

    def set_liquid_thermal_diffusivity(self, niul):
        self.niu_l = niul

    def set_rock_thermal_diffusivity(self, niurock):
        self.niu_solid = niurock

    def set_bc_adiabatic_x_left(self, bc_ad):
        if (bc_ad==True):
            self.solute_bc_x_left = 2

    def set_bc_adiabatic_x_right(self, bc_ad):
        if (bc_ad==True):
            self.solute_bc_x_right = 2

    def set_bc_adiabatic_y_left(self, bc_ad):
        if (bc_ad==True):
            self.solute_bc_y_left = 2

    def set_bc_adiabatic_y_right(self, bc_ad):
        if (bc_ad==True):
            self.solute_bc_y_right = 2

    def set_bc_adiabatic_z_left(self, bc_ad):
        if (bc_ad==True):
            self.solute_bc_z_left = 2

    def set_bc_adiabatic_z_right(self, bc_ad):
        if (bc_ad==True):
            self.solute_bc_z_right = 2
    
    def set_bc_constant_temperature_x_left(self,xl):
        self.solute_bc_x_left = 1
        self.solute_bcxl = xl
    
    def set_bc_constant_temperature_x_right(self,xr):
        self.solute_bc_x_right = 1
        self.solute_bcxr = xr
    
    def set_bc_constant_temperature_y_left(self,yl):
        self.solute_bc_y_left = 1
        self.solute_bcyl = yl

    def set_bc_constant_temperature_y_right(self,yr):
        self.solute_bc_y_right = 1
        self.solute_bcyr = yr

    def set_bc_constant_temperature_z_left(self,zl):
        self.solute_bc_z_left = 1
        self.solute_bczl = zl

    def set_bc_constant_temperature_z_right(self,zr):
        self.solute_bc_z_right = 1
        self.solute_bczr = zr

    
    def update_H_sl(self):
        self.H_s = self.Cp_s*self.T_s
        self.H_l = self.H_s+self.Lt
        print('H_s',self.H_s)
        print('H_l',self.H_l)


    @ti.kernel
    def init_H(self):
        for I in ti.grouped(self.rho_T):
            self.rho_H[I] = self.convert_T_H(self.rho_T[I])
    
    
    @ti.kernel
    def init_fg(self):
        for I in ti.grouped(self.fg):
            Cp = self.rho_fl[I]*self.Cp_l + (1-self.rho_fl[I])*self.Cp_s
            for s in ti.static(range(19)):
                self.fg[I][s] = self.g_feq(s,self.rho_T[I],self.rho_H[I], Cp, self.v[I])
                self.Fg[I][s] = self.fg[I][s]

    @ti.kernel
    def init_fl(self):
        for I in ti.grouped(self.rho_T):
            self.rho_fl[I] = self.convert_T_fl(self.rho_T[I])

    @ti.func
    def g_feq(self, k,local_T,local_H, Cp, u):
        eu = self.e[k].dot(u)
        uv = u.dot(u)
        feqout = 0.0
        if (k==0):
            feqout = local_H-Cp*local_T+self.w[k]*Cp*local_T*(1-1.5*uv)
        else:
            feqout = self.w[k]*Cp*local_T*(1.0+3.0*eu+4.5*eu*eu-1.5*uv)
        #print(k, self.w[k], feqout, Cp, local_T)
        return feqout

    
    @ti.func
    def cal_local_force(self, i, j, k):
        f = ti.Vector([self.fx, self.fy, self.fz])
        f[1] += self.gravity*self.buoyancy_parameter*(self.rho_T[i,j,k]-self.ref_T)
        f *= self.rho_fl[i,j,k]
        return f
    

    @ti.kernel
    def colission_g(self):
        for I in ti.grouped(self.rho_T):
            #tau_s = 3.0*self.niu_solid+0.5
            #Cp = self.Cp_solid
            
            tau_s = 3*(self.niu_s*(1.0-self.rho_fl[I])+self.niu_l*self.rho_fl[I])+0.5
            Cp = self.rho_fl[I]*self.Cp_l + (1-self.rho_fl[I])*self.Cp_s

            #ROCK 
            if (self.solid[I] >0):
                tau_s = 3.0*self.niu_solid+0.5
                Cp = self.Cp_solid
    

            for s in ti.static(range(19)):
                tmp_fg = -1.0/tau_s*(self.fg[I][s]-self.g_feq(s,self.rho_T[I],self.rho_H[I], Cp, self.v[I]))
                #print(self.fg[I][s],tmp_fg,I,s,self.rho_H[I],self.g_feq(s,self.rho_T[I],self.rho_H[I], Cp, self.v[I]))
                self.fg[I][s] += tmp_fg
            


    
    @ti.kernel
    def colission(self):
        for i,j,k in self.rho:
            #if (self.solid[i,j,k] == 0):
            m_temp = self.M[None]@self.F[i,j,k]
            meq = self.meq_vec(self.rho[i,j,k],self.v[i,j,k])
            m_temp -= self.S_dig[None]*(m_temp-meq)
            f = self.cal_local_force(i,j,k)
            if (ti.static(self.force_flag==1)):
                for s in ti.static(range(19)):
                #    m_temp[s] -= S_dig[s]*(m_temp[s]-meq[s])
                    #f = self.cal_local_force()
                    f_guo=0.0
                    for l in ti.static(range(19)):
                        f_guo += self.w[l]*((self.e_f[l]-self.v[i,j,k]).dot(f)+(self.e_f[l].dot(self.v[i,j,k])*(self.e_f[l].dot(f))))*self.M[None][s,l]
                    #m_temp[s] += (1-0.5*self.S_dig[None][s])*self.GuoF(i,j,k,s,self.v[i,j,k],force)
                    m_temp[s] += (1-0.5*self.S_dig[None][s])*f_guo
            
            self.f[i,j,k] = ti.Vector([0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0])
            self.f[i,j,k] += self.inv_M[None]@m_temp

            for s in ti.static(range(19)):
                self.f[i,j,k][s] = self.f[i,j,k][s]*(self.rho_fl[i,j,k]) + self.w[s]*(1.0-self.rho_fl[i,j,k])
    
    @ti.kernel
    def streaming1(self):
        for i in ti.grouped(self.rho):
            #if (self.solid[i] == 0):
            for s in ti.static(range(19)):
                ip = self.periodic_index(i+self.e[s])
                self.F[ip][s] = self.f[i][s]
                #if (self.solid[ip]==0):
                #    self.F[ip][s] = self.f[i][s]
                #else:
                #    self.F[i][self.LR[s]] = self.f[i][s]
                    

    
    @ti.kernel
    def streaming1_g(self):
        for i in ti.grouped(self.rho_T):
            for s in ti.static(range(19)):
                ip = self.periodic_index(i+self.e[s])
                self.Fg[ip][s] = self.fg[i][s]
                #if (self.solid[ip]==0):
                #    self.Fg[ip][s] = self.fg[i][s]
                #else:
                #    self.Fg[i][self.LR[s]] = self.fg[i][s] # adiabatic BC!!!
                
                
                    #self.Fg[i][s] = self.fg[i][s] # adiabatic BC!!!
                #self.Fg[ip][s] = self.fg[i][s]

    @ti.kernel
    def BC_concentration(self):
        if ti.static(self.solute_bc_x_left==1):
            for j,k in ti.ndrange((0,self.ny),(0,self.nz)):
                local_T = self.solute_bcxl
                local_H = self.convert_T_H(local_T)
                Cp = self.rho_fl[0,j,k]*self.Cp_l + (1-self.rho_fl[0,j,k])*self.Cp_s

                for s in ti.static(range(19)):
                    self.fg[0,j,k][s] = self.g_feq(s,local_T, local_H, Cp, self.v[0,j,k])
                    self.Fg[0,j,k][s] = self.fg[0,j,k][s]
        elif ti.static(self.solute_bc_x_left==2):
            for j,k in ti.ndrange((0,self.ny),(0,self.nz)):
                for s in ti.static(range(19)):
                    self.fg[0,j,k][s] = self.fg[1,j,k][s]
                    self.Fg[0,j,k][s] = self.fg[1,j,k][s]


        if ti.static(self.solute_bc_x_right==1):
            for j,k in ti.ndrange((0,self.ny),(0,self.nz)):
                local_T = self.solute_bcxr
                local_H = self.convert_T_H(local_T)
                Cp = self.rho_fl[self.nx-1,j,k]*self.Cp_l + (1-self.rho_fl[self.nx-1,j,k])*self.Cp_s

                for s in ti.static(range(19)):
                    self.fg[self.nx-1,j,k][s] = self.g_feq(s,local_T, local_H, Cp, self.v[self.nx-1,j,k])
                    self.Fg[self.nx-1,j,k][s]= self.fg[self.nx-1,j,k][s]
        elif ti.static(self.solute_bc_x_right==2):
            for j,k in ti.ndrange((0,self.ny),(0,self.nz)):
                for s in ti.static(range(19)):
                    self.fg[self.nx-1,j,k][s] = self.fg[self.nx-2,j,k][s]
                    self.Fg[self.nx-1,j,k][s] = self.fg[self.nx-2,j,k][s]


        if ti.static(self.solute_bc_y_left==1):
            for i,k in ti.ndrange((0,self.nx),(0,self.nz)):
                local_T = self.solute_bcyl
                local_H = self.convert_T_H(local_T)
                Cp = self.rho_fl[i,0,k]*self.Cp_l + (1-self.rho_fl[i,0,k])*self.Cp_s

                for s in ti.static(range(19)):
                    self.fg[i,0,k][s] = self.g_feq(s,local_T, local_H, Cp, self.v[i,0,k])
                    self.Fg[i,0,k][s] = self.fg[i,0,k][s]
        elif ti.static(self.solute_bc_y_left==2):
            for i,k in ti.ndrange((0,self.nx),(0,self.nz)):
                for s in ti.static(range(19)):
                    self.fg[i,0,k][s] = self.fg[i,1,k][s]
                    self.Fg[i,0,k][s] = self.fg[i,1,k][s]


        if ti.static(self.solute_bc_y_right==1):
            for i,k in ti.ndrange((0,self.nx),(0,self.nz)):
                local_T = self.solute_bcyr
                local_H = self.convert_T_H(local_T)
                Cp = self.rho_fl[i,self.ny-1,k]*self.Cp_l + (1-self.rho_fl[i,self.ny-1,k])*self.Cp_s

                for s in ti.static(range(19)):
                    self.fg[i,self.ny-1,k][s] = self.g_feq(s,local_T, local_H, Cp, self.v[i,self.ny-1,k])
                    self.Fg[i,self.ny-1,k][s] = self.fg[i,self.ny-1,k][s]
        elif ti.static(self.solute_bc_y_right==2):
            for i,k in ti.ndrange((0,self.nx),(0,self.nz)):
                for s in ti.static(range(19)):
                    self.fg[i,self.ny-1,k][s] = self.fg[i,self.ny-2,k][s]
                    self.Fg[i,self.ny-1,k][s] = self.fg[i,self.ny-2,k][s]


        if ti.static(self.solute_bc_z_left==1):
            for i,j in ti.ndrange((0,self.nx),(0,self.ny)):
                local_T = self.solute_bczl
                local_H = self.convert_T_H(local_T)
                Cp = self.rho_fl[i,j,0]*self.Cp_l + (1-self.rho_fl[i,j,0])*self.Cp_s

                for s in ti.static(range(19)):
                    self.fg[i,j,0][s] = self.g_feq(s,local_T, local_H, Cp, self.v[i,j,0])
                    self.Fg[i,j,0][s] = self.fg[i,j,0][s]
        elif ti.static(self.solute_bc_z_left==1):
            for i,j in ti.ndrange((0,self.nx),(0,self.ny)):
                for s in ti.static(range(19)):
                    self.fg[i,j,0][s] = self.fg[i,j,1][s]
                    self.Fg[i,j,0][s] = self.fg[i,j,1][s]


        if ti.static(self.solute_bc_z_right==1):
            for i,j in ti.ndrange((0,self.nx),(0,self.ny)):
                local_T = self.solute_bczr
                local_H = self.convert_T_H(local_T)
                Cp = self.rho_fl[i,j,self.nz-1]*self.Cp_l + (1-self.rho_fl[i,j,self.nz-1])*self.Cp_s

                for s in ti.static(range(19)):
                    self.fg[i,j,self.nz-1][s] = self.g_feq(s,local_T, local_H, Cp, self.v[i,j,self.nz-1])
                    self.Fg[i,j,self.nz-1][s] = self.fg[i,j,self.nz-1][s]
        elif ti.static(self.solute_bc_z_right==1):
            for i,j in ti.ndrange((0,self.nx),(0,self.ny)):
                for s in ti.static(range(19)):
                    self.fg[i,j,self.nz-1][s] = self.fg[i,j,self.nz-2][s]
                    self.Fg[i,j,self.nz-1][s] = self.fg[i,j,self.nz-2][s]

    @ti.func
    def convert_H_T(self,local_H):
        new_T=0.0
        if (local_H<self.H_s):
            new_T = local_H/self.Cp_s
        elif (local_H>self.H_l):
            new_T = self.T_l+(local_H-self.H_l)/self.Cp_l
        elif (self.T_l>self.T_s):
            new_T = self.T_s+(local_H-self.H_s)/(self.H_l-self.H_s)*(self.T_l-self.T_s)
        else:
            new_T = self.T_s

        return new_T

    @ti.func
    def convert_H_fl(self,local_H):
        new_fl=0.0
        if (local_H<self.H_s):
            new_fl = 0.0
        elif (local_H>self.H_l):
            new_fl = 1.0
        else:
            new_fl = (local_H-self.H_s)/(self.H_l-self.H_s)

        return new_fl


    @ti.func
    def convert_T_H(self,local_T):
        new_H = 0.0
        if (local_T<=self.T_s):
            new_H = self.Cp_s*local_T
        elif (local_T>self.T_l):
            new_H = (local_T-self.T_l)*self.Cp_l+self.H_l
        else:
            fluid_frc = (local_T-self.T_s)/(self.T_l-self.T_s)
            new_H = self.H_s*(1-fluid_frc) + self.H_l*fluid_frc
        return new_H

    @ti.func
    def convert_T_fl(self,local_T):
        new_fl = 0.0
        if (local_T<=self.T_s):
            new_fl = 0.0
        elif (local_T>=self.T_l):
            new_fl = 1.0
        elif (self.T_l>self.T_s):
            new_fl = (local_T-self.T_s)/(self.T_l-self.T_s)
        else:
            new_fl = 1.0

        return new_fl

    @ti.kernel
    def streaming3(self):
        for i in ti.grouped(self.rho):
            self.forcexyz[i] = self.cal_local_force(i.x, i.y, i.z)
            #print(i.x, i.y, i.z)
            if ((self.solid[i]==0) or (self.rho_fl[i]>0.0)):
                self.rho[i] = 0
                self.v[i] = ti.Vector([0,0,0])
                self.f[i] = self.F[i]
                for s in ti.static(range(19)):
                    self.f[i][s] = self.f[i][s]*self.rho_fl[i]+self.w[s]*(1.0-self.rho_fl[i])
                self.rho[i] += self.f[i].sum()

                for s in ti.static(range(19)):
                    self.v[i] += self.e_f[s]*self.f[i][s]
                
                f = self.cal_local_force(i.x, i.y, i.z)

                self.v[i] /= self.rho[i]
                self.v[i] += (f/2)/self.rho[i]
                
            else:
                self.rho[i] = 1.0
                self.v[i] = ti.Vector([0,0,0])

    @ti.kernel
    def streaming3_g(self):
        for i in ti.grouped(self.rho_T):
            self.rho_H[i] = 0.0
            self.rho_H[i] = self.Fg[i].sum()
            #for s in ti.static(range(19)):
            #    self.rho_H[i] += self.Fg[i][s]
            self.fg[i] = self.Fg[i]

    @ti.kernel
    def update_T_fl(self):
        for I in ti.grouped(self.rho_T):
            self.rho_T[I] = self.convert_H_T(self.rho_H[I])
            self.rho_fl[I] = self.convert_H_fl(self.rho_H[I])
            if (self.solid[I]>0):
                self.rho_fl[I] = 0.0


    def init_solute_simulation(self):

        self.init_simulation()
        self.update_H_sl()
        self.init_H()
        self.init_fl()
        self.init_fg()
        
    def init_concentration(self,filename):
        in_dat = np.loadtxt(filename)
        in_dat = np.reshape(in_dat, (self.nx,self.ny,self.nz),order='F')
        self.rho_T.from_numpy(in_dat)


    def step(self):
        self.colission()
        self.colission_g()
        
        self.streaming1()
        self.streaming1_g()

        self.Boundary_condition()
        self.BC_concentration()

        self.streaming3_g()
        self.streaming3()
        self.streaming3_g()

        self.update_T_fl()

    def export_VTK(self, n):
        gridToVTK(
                "./LB_SingelPhase_"+str(n),
                self.x,
                self.y,
                self.z,
                #cellData={"pressure": pressure},
                pointData={ "Solid": np.ascontiguousarray(self.solid.to_numpy()),
                            "rho": np.ascontiguousarray(self.rho.to_numpy()),
                            "Solid_Liquid": np.ascontiguousarray(self.rho_fl.to_numpy()),
                            "Tempreture": np.ascontiguousarray(self.rho_T.to_numpy()),
                            "Entropy": np.ascontiguousarray(self.rho_H.to_numpy()),
                            "velocity": (   np.ascontiguousarray(self.v.to_numpy()[0:self.nx,0:self.ny,0:self.nz,0]), 
                                            np.ascontiguousarray(self.v.to_numpy()[0:self.nx,0:self.ny,0:self.nz,1]),
                                            np.ascontiguousarray(self.v.to_numpy()[0:self.nx,0:self.ny,0:self.nz,2])),
                            "Force": (      np.ascontiguousarray(self.forcexyz.to_numpy()[0:self.nx,0:self.ny,0:self.nz,0]), 
                                            np.ascontiguousarray(self.forcexyz.to_numpy()[0:self.nx,0:self.ny,0:self.nz,1]),
                                            np.ascontiguousarray(self.forcexyz.to_numpy()[0:self.nx,0:self.ny,0:self.nz,2]))
                            }
            )   


'''
time_init = time.time()
time_now = time.time()
time_pre = time.time()
dt_count = 0            


lb3d_solute = LB3D_Solver_Single_Phase_Solute(50,50,5)
lb3d_solute.init_geo('./geo_cavity.dat')
lb3d_solute.init_concentration('./psi.dat')

lb3d_solute.set_force([0e-6,-1.0e-6,0.0])
lb3d_solute.set_viscosity(0.05)
lb3d_solute.init_solute_simulation()


for iter in range(300000+1):
    lb3d_solute.step()

    if (iter%1000==0):
        
        time_pre = time_now
        time_now = time.time()
        diff_time = int(time_now-time_pre)
        elap_time = int(time_now-time_init)
        m_diff, s_diff = divmod(diff_time, 60)
        h_diff, m_diff = divmod(m_diff, 60)
        m_elap, s_elap = divmod(elap_time, 60)
        h_elap, m_elap = divmod(m_elap, 60)

        max_v = lb3d_solute.get_max_v()
        
        print('----------Time between two outputs is %dh %dm %ds; elapsed time is %dh %dm %ds----------------------' %(h_diff, m_diff, s_diff,h_elap,m_elap,s_elap))
        print('The %dth iteration, Max Force = %f,  force_scale = %f\n\n ' %(iter, max_v,  10.0))
        
        if (iter%5000==0):
            lb3d_solute.export_VTK(iter)
'''

            


#ti.profiler.print_scoped_profiler_info()
#ti.print_profile_info()
#ti.profiler.print_kernel_profiler_info()  # default mode: 'count'

#ti.profiler.print_kernel_profiler_info('trace')
#ti.profiler.clear_kernel_profiler_info()  # clear all records
