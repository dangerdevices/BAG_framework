# -*- coding: utf-8 -*-
########################################################################################################################
#
# Copyright (c) 2014, Regents of the University of California
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification, are permitted provided that the
# following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following
#   disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the
#    following disclaimer in the documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
# INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
# WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
########################################################################################################################

"""This module defines functions and classes useful for characterizing linear time-invariant circuits.
"""

from typing import Dict, List

import numpy as np
import scipy.signal
import scipy.sparse
import scipy.sparse.linalg
from scipy.signal.ltisys import TransferFunctionContinuous


class LTICircuit(object):
    """A class that models a linear-time-invariant circuit.

    This class computes AC transfer functions for linear-time-invariant circuits.  Currently
    we support resistors, capacitors, voltage controlled current sources, and small-signal model transistors.

    Note: Since this class work with Ac transfer functions, 'gnd' in this circuit is AC ground.
    """
    def __init__(self):
        # type: (List[str]) -> None
        self._n = 0
        self._gmat_data = {}
        self._cmat_data = {}
        self._node_id = {'gnd': -1, 'vss': -1, 'vdd': -1}

    def _get_node_id(self, name):
        # type: (str) -> int
        if name not in self._node_id:
            ans = self._n
            self._node_id[name] = ans
            self._n += 1
            return ans
        else:
            return self._node_id[name]

    def add_res(self, res, p_name, n_name):
        # type: (float, str, str) -> None
        """Adds a resistor to the circuit.

        Parameters
        ----------
        res : float
            the resistance value, in Ohms.
        p_name : str
            the positive terminal net name.
        n_name : str
            the negative terminal net name.
        """
        node_p = self._get_node_id(p_name)
        node_n = self._get_node_id(n_name)

        if node_p == node_n:
            return
        if node_p < node_n:
            node_p, node_n = node_n, node_p

        g = 1 / res
        self._gmat_data[(node_p, node_p)] += g
        if node_n >= 0:
            self._gmat_data[(node_p, node_n)] -= g
            self._gmat_data[(node_n, node_n)] += g
            self._gmat_data[(node_n, node_p)] -= g

    def add_gm(self, gm, p_name, n_name, cp_name, cn_name='gnd'):
        # type: (float, str, str, str, str) -> None
        """Adds a voltage controlled current source to the circuit.

        Parameters
        ----------
        gm : float
            the gain of the voltage controlled current source, in Siemens.
        p_name : str
            the terminal that the current flows out of.
        n_name : str
            the terminal that the current flows in to.
        cp_name : str
            the positive voltage control terminal.
        cn_name : str
            the negative voltage control terminal.  Defaults to 'gnd'.
        """
        node_p = self._get_node_id(p_name)
        node_n = self._get_node_id(n_name)
        node_cp = self._get_node_id(cp_name)
        node_cn = self._get_node_id(cn_name)

        if node_p == node_n or node_cp == node_cn:
            return

        if node_cp >= 0:
            if node_p >= 0:
                self._gmat_data[(node_p, node_cp)] += gm
            if node_n >= 0:
                self._gmat_data[(node_n, node_cp)] -= gm
        if node_cn >= 0:
            if node_p >= 0:
                self._gmat_data[(node_p, node_cn)] -= gm
            if node_n >= 0:
                self._gmat_data[(node_n, node_cn)] += gm

    def add_cap(self, cap, p_name, n_name):
        # type: (float, str, str) -> None
        """Adds a capacitor to the circuit.

        Parameters
        ----------
        cap : float
            the capacitance value, in Farads.
        p_name : str
            the positive terminal net name.
        n_name : str
            the negative terminal net name.
        """
        node_p = self._get_node_id(p_name)
        node_n = self._get_node_id(n_name)

        if node_p == node_n:
            return
        if node_p < node_n:
            node_p, node_n = node_n, node_p

        self._cmat_data[(node_p, node_p)] += cap
        if node_n >= 0:
            self._cmat_data[(node_p, node_n)] -= cap
            self._cmat_data[(node_n, node_n)] += cap
            self._cmat_data[(node_n, node_p)] -= cap

    def add_transistor(self, tran_info, d_name, g_name, s_name, b_name='gnd', fg=1):
        # type: (Dict[str, float], str, str, str, str, int) -> None
        """Adds a small signal transistor model to the circuit.

        Parameters
        ----------
        tran_info : Dict[str, float]
            a dictionary of 1-finger transistor small signal parameters.  Should contain gm, gds, gb,
            cgd, cgs, cgb, cds, cdb, and csb.
        d_name : str
            drain net name.
        g_name : str
            gate net name.
        s_name : str
            source net name.
        b_name : str
            body net name.  Defaults to 'gnd'.
        fg : int
            number of transistor fingers.
        """
        gm = tran_info['gm'] * fg
        ro = 1 / (tran_info['gds'] * fg)
        gb = tran_info['gb'] * fg
        cgd = tran_info['cgd'] * fg
        cgs = tran_info['cgs'] * fg
        cgb = tran_info['cgb'] * fg
        cds = tran_info['cds'] * fg
        cdb = tran_info['cdb'] * fg
        csb = tran_info['csb'] * fg

        self.add_gm(gm, d_name, s_name, g_name, s_name)
        self.add_res(ro, d_name, s_name)
        self.add_gm(gb, d_name, s_name, b_name, s_name)
        self.add_cap(cgd, g_name, d_name)
        self.add_cap(cgs, g_name, s_name)
        self.add_cap(cgb, g_name, b_name)
        self.add_cap(cds, d_name, s_name)
        self.add_cap(cdb, d_name, b_name)
        self.add_cap(csb, s_name, b_name)

    @staticmethod
    def dict_to_csc_mat(table, shape, ignore_row=-1, ignore_col=-1):
        row_list = []
        col_list = []
        data_list = []
        for (row, col), data in table.items():
            if row != ignore_row and col != ignore_col:
                row_list.append(row)
                col_list.append(col)
                data_list.append(data)

        return scipy.sparse.csc_matrix((data_list, (row_list, col_list)), shape=shape)

    def get_voltage_gain_system(self, in_name, out_name, atol=0.0):
        # type: (str, str, float) -> TransferFunctionContinuous
        """Computes and return the voltage gain transfer function between the two given nodes.

        Parameters
        ----------
        in_name : str
            the input node name.  An ideal voltage source will be connected to this node.
        out_name : str
            the output node name.  The output will be the voltage on this node.
        atol : float
            absolute-tolerance for checking if transfer function numerator coefficients are zeroes.
            If you get scipy bad-conditioning warnings consider tweaking this parameter.

        Returns
        -------
        system : TransferFunctionContinuous
            the scipy transfer function object.  See scipy.signal package on how to use this object.
        """
        node_in = self._node_id[in_name]
        node_out = self._node_id[out_name]
        if node_in == node_out:
            raise ValueError('Input and output nodes are the same.')

        mat_shape = (self._n - 1, self._n)
        gmat = self.dict_to_csc_mat(self._gmat_data, mat_shape, ignore_row=node_in)
        cmat = self.dict_to_csc_mat(self._cmat_data, mat_shape, ignore_row=node_in)

        # separate input voltage from state space
        col_core = [idx for idx in range(self._n) if idx != node_in]
        cmat_core = cmat[:, col_core]
        gmat_core = gmat[:, col_core]

        try:
            solve_fun = scipy.sparse.linalg.factorized(cmat_core)
        except RuntimeError:
            raise ValueError('cap matrix is singular.')

        cvec_in = cmat[:, node_in:node_in + 1]
        gvec_in = gmat[:, node_in:node_in + 1]

        if node_out > node_in:
            node_out -= 1

        # modify state variables so we don't have input derivative term
        weight_vec = solve_fun(cvec_in)
        gvec_in -= np.dot(gmat_core, weight_vec)
        dmat = np.ones((1, 1)) * -weight_vec[node_out, 0]

        # construct state space model.
        amat = solve_fun(-gmat_core)
        bmat = solve_fun(-gvec_in)
        cmat = np.zeros((1, self._n - 1))
        cmat[0, node_out] = 1

        num, den = scipy.signal.ss2tf(amat, bmat, cmat, dmat)
        num = num[0, :]
        # check if numerator has leading zeros.
        # this makes it so the user have full control over numerical precision, and
        # avoid scipy bad conditioning warnings.
        while abs(num[0]) <= atol:
            num = num[1:]
        return TransferFunctionContinuous(num, den)

    def get_impedance_gain_system(self, in_name, out_name, short_name='', atol=0.0):
        # type: (str, str, str, float) -> TransferFunctionContinuous
        """Computes and return the impedance gain transfer function between the two given nodes.

        Parameters
        ----------
        in_name : str
            the input node name.  An ideal current source will be connected to this node.
        out_name : str
            the output node name.  The output will be the voltage on this node.
        short_name : str
            if not empty, this node will be shorted to ground.  This is useful for computing output impedance.
        atol : float
            absolute-tolerance for checking if transfer function numerator coefficients are zeroes.
            If you get scipy bad-conditioning warnings consider tweaking this parameter.

        Returns
        -------
        system : TransferFunctionContinuous
            the scipy transfer function object.  See scipy.signal package on how to use this object.
        """
        node_in = self._node_id[in_name]
        node_out = self._node_id[out_name]

        if short_name:
            node_short = self._node_id[short_name]
            if node_in == node_short or node_out == node_short:
                raise ValueError('Shorting input/output.')

            # remove node that's shorted to ground
            mat_shape = (self._n - 1, self._n - 1)
            gmat = self.dict_to_csc_mat(self._gmat_data, mat_shape, ignore_row=node_short, ignore_col=node_short)
            cmat = self.dict_to_csc_mat(self._cmat_data, mat_shape, ignore_row=node_short, ignore_col=node_short)
            if node_in > node_short:
                node_in -= 1
            if node_out > node_short:
                node_out -= 1
        else:
            mat_shape = (self._n, self._n)
            gmat = self.dict_to_csc_mat(self._gmat_data, mat_shape)
            cmat = self.dict_to_csc_mat(self._cmat_data, mat_shape)

        try:
            solve_fun = scipy.sparse.linalg.factorized(cmat)
        except RuntimeError:
            raise ValueError('cap matrix is singular.')

        bmat = np.zeros((mat_shape[0], 1))
        bmat[node_in, 0] = -1

        # construct state space model
        amat = solve_fun(-gmat)
        bmat = solve_fun(-bmat)
        cmat = np.zeros((1, mat_shape[0]))
        cmat[0, node_out] = 1
        dmat = np.zeros((1, 1))

        num, den = scipy.signal.ss2tf(amat, bmat, cmat, dmat)
        num = num[0, :]
        # check if numerator has leading zeros.
        # this makes it so the user have full control over numerical precision, and
        # avoid scipy bad conditioning warnings.
        while abs(num[0]) <= atol:
            num = num[1:]
        return TransferFunctionContinuous(num, den)

    def get_impedance(self, node_name, freq, short_name='', atol=0.0):
        # type: (str, float, str, float) -> complex
        """Computes the impedance looking into the given node.

        Parameters
        ----------
        node_name : str
            the node to compute impedance for.  We will inject a current into this node and measure the voltage
            on this node.
        freq : float
            the frequency to compute the impedance at, in Hertz.
        short_name : str
            if not empty, this node will be shorted to ground.  This is useful for computing output impedance.
        atol : float
            absolute-tolerance for checking if transfer function numerator coefficients are zeroes.
            If you get scipy bad-conditioning warnings consider tweaking this parameter.

        Returns
        -------
        impedance : complex
            the impedance value, in Ohms.
        """
        sys = self.get_impedance_gain_system(node_name, node_name, short_name=short_name, atol=atol)
        w_test = 2 * np.pi * freq
        _, zin_vec = sys.freqresp(w=[w_test])
        return zin_vec[0]
