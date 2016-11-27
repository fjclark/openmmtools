#!/usr/bin/env python

# =============================================================================
# MODULE DOCSTRING
# =============================================================================

"""
Classes that represent a portion of the state of an OpenMM context.

"""


# =============================================================================
# GLOBAL IMPORTS
# =============================================================================

import copy

from simtk import openmm


# =============================================================================
# CUSTOM EXCEPTIONS
# =============================================================================

class ThermodynamicsError(Exception):

    # TODO substitute this with enum when we drop Python 2.7 support
    (NO_BAROSTAT,
     MULTIPLE_BAROSTATS,
     UNSUPPORTED_BAROSTAT,
     INCONSISTENT_BAROSTAT,
     BAROSTATED_NONPERIODIC) = range(5)

    error_messages = {
        NO_BAROSTAT: "System is incompatible with NPT ensemble: missing barostat.",
        MULTIPLE_BAROSTATS: "System has multiple barostats.",
        UNSUPPORTED_BAROSTAT: "Found unsupported barostat {} in system.",
        INCONSISTENT_BAROSTAT: "System barostat is inconsistent with thermodynamic state.",
        BAROSTATED_NONPERIODIC: "Cannot set pressure of non-periodic system."
    }

    def __init__(self, code, *args):
        error_message = self.error_messages[code].format(*args)
        super(ThermodynamicsError, self).__init__(error_message)
        self.code = code


# =============================================================================
# THERMODYNAMIC STATE
# =============================================================================

class ThermodynamicState(object):
    """The state of a Context that does not change with integration."""

    # -------------------------------------------------------------------------
    # Public interface
    # -------------------------------------------------------------------------

    def __init__(self, system, temperature, pressure=None, force_system_state=False):
        """Constructor."""
        system = copy.deepcopy(system)  # do not modify original system

        self._temperature = temperature
        self._system = system

        # Check system compatibility
        if pressure is not None:
            barostat = self._barostat
            if barostat is None and force_system_state:
                self._add_barostat(pressure)
            elif barostat is None and not force_system_state:
                raise ThermodynamicsError(ThermodynamicsError.NO_BAROSTAT)
            elif not force_system_state and not self._is_barostat_consistent(barostat):
                raise ThermodynamicsError(ThermodynamicsError.INCONSISTENT_BAROSTAT)
            elif force_system_state:
                self._configure_barostat(pressure)

    @property
    def system(self):
        return copy.deepcopy(self._system)

    @property
    def pressure(self):
        barostat = self._barostat
        if barostat is None:
            return None
        return barostat.getDefaultPressure()

    @pressure.setter
    def pressure(self, value):
        if not self._system.usesPeriodicBoundaryConditions():
            raise ThermodynamicsError(ThermodynamicsError.BAROSTATED_NONPERIODIC)
        barostat = self._barostat
        if barostat is None:
            self._add_barostat(value)
        else:
            self._configure_barostat(value)

    # -------------------------------------------------------------------------
    # Internal-usage: barostat handling
    # -------------------------------------------------------------------------

    _SUPPORTED_BAROSTATS = {'MonteCarloBarostat'}

    @property
    def _barostat(self):
        """Shortcut for _find_barostat(self._system)."""
        return self._find_barostat(self._system)

    @classmethod
    def _find_barostat(cls, system):
        """Return the first barostat found in the system.

        Parameters
        ----------
        system : simtk.openmm.System
            The OpenMM system containing the barostat.

        Returns
        -------
        barostat : OpenMM Force object
            The barostat in system or None if no barostat is found.

        Raises
        ------
        ThermodynamicsError
            If the system contains multiple or unsupported barostats.

        """
        barostat_forces = [force for force in system.getForces()
                           if 'Barostat' in force.__class__.__name__]
        if len(barostat_forces) == 0:
            return None
        if len(barostat_forces) > 1:
            raise ThermodynamicsError(ThermodynamicsError.MULTIPLE_BAROSTATS)

        barostat = barostat_forces[0]
        if barostat.__class__.__name__ not in cls._SUPPORTED_BAROSTATS:
            raise ThermodynamicsError(ThermodynamicsError.UNSUPPORTED_BAROSTAT,
                                          barostat.__class__.__name__)
        return barostat

    def _is_barostat_consistent(self, barostat):
        """Check the barostat's temperature and pressure."""
        try:
            barostat_temperature = barostat.getDefaultTemperature()
        except AttributeError:  # versions previous to OpenMM 7.1
            barostat_temperature = barostat.getTemperature()
        barostat_pressure = barostat.getDefaultPressure()
        is_consistent = barostat_temperature == self._temperature
        is_consistent = is_consistent and barostat_pressure == self.pressure
        return is_consistent

    def _configure_barostat(self, pressure):
        """Configure the barostat to be consistent with this state."""
        barostat = self._barostat
        try:
            barostat.setDefaultTemperature(self._temperature)
        except AttributeError:  # versions previous to OpenMM 7.1
            barostat.setTemperature(self._temperature)
        barostat.setDefaultPressure(pressure)

    def _add_barostat(self, pressure):
        """Add a MonteCarloBarostat to the given system."""
        assert self._barostat is None  # pre-condition
        barostat = openmm.MonteCarloBarostat(pressure, self._temperature)
        self._system.addForce(barostat)
