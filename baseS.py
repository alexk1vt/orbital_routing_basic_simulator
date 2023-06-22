# baseS.py

# A class for base S representation of numbers where S is the number of satellites per orbit
class baseS:
    def __init__(self, decimalValue, num_orbits, sats_per_orbit):
        assert sats_per_orbit < 37, "sats_per_orbit must be less than 37" # can't represent more than base 36 with current implementation
        assert type(decimalValue) == int, "decimalValue must be an integer"
        #assert decimalValue >= 0, "decimalValue must be positive"
        assert abs(decimalValue) <= num_orbits*2, "decimalValue must not be greater than twice the number of orbits" # can't represent more than 2 digits with current implementation
        self.digits = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        self.S = sats_per_orbit
        self.P = num_orbits
        self.decimalValue = decimalValue
        self.baseS = self.digits[:sats_per_orbit]
        self.baseSStr = self.dec2baseS(decimalValue)

    @classmethod
    def fromBaseS(cls, baseSnum):
        return cls(baseSnum.getDecimalValue(), baseSnum.getP(), baseSnum.getS())
    
    @classmethod
    def copyBaseSfromDecimal(cls, baseSinstance, decimalValue):
        return cls(decimalValue, baseSinstance.getP(), baseSinstance.getS())
        
    # function to convert integer to base S
    def dec2baseS(self, decimalNum):
        if abs(decimalNum) < self.S: # single digit
            if decimalNum < 0:
                return "-" + self.baseS[-decimalNum]
            return self.baseS[decimalNum]
        else: # two digits
            if decimalNum < 0:
                return "-" + self.baseS[-decimalNum // self.S] + self.dec2baseS(-decimalNum % self.S)
            return self.baseS[decimalNum // self.S] + self.dec2baseS(decimalNum % self.S)
    
    # function to convert base 22 to integer
    def baseS2dec(self, baseSStr):
        if baseSStr[0] == "-":
            baseSStr = baseSStr[1:]
            negative = True
        else:
            negative = False
        if len(baseSStr) == 1:
            if negative:
                return -self.baseS.index(baseSStr)
            return self.baseS.index(baseSStr)
        else:
            if negative:
                return -self.baseS.index(baseSStr[0]) * self.S + self.baseS2dec(baseSStr[1:])
            return self.baseS.index(baseSStr[0]) * self.S + self.baseS2dec(baseSStr[1:])
    
    def getDecimalValue(self):
        return self.decimalValue
    
    def getS(self):
        return self.S
    
    def getP(self):
        return self.P

    def __str__(self):
        return self.baseSStr
    
    def __repr__(self):
        return self.baseSStr
    
    def __add__(self, other):
        if type(other) == int:
            return self.copyBaseSfromDecimal(self, self.getDecimalValue() + other)
        return self.copyBaseSfromDecimal(self, self.getDecimalValue() + other.getDecimalValue())
    
    def __radd__(self, other):
        if type(other) == int:
            return self.copyBaseSfromDecimal(self, self.getDecimalValue() + other)
        return self.copyBaseSfromDecimal(self, self.getDecimalValue() + other.getDecimalValue())

    def __sub__(self, other):
        if type(other) == int:
            return self.copyBaseSfromDecimal(self, self.getDecimalValue() - other)
        return self.copyBaseSfromDecimal(self, self.getDecimalValue() - other.getDecimalValue())
    
    def __mul__(self, other):
        return self.copyBaseSfromDecimal(self, self.getDecimalValue() * other.getDecimalValue())
    
    def __truediv__(self, other):
        return self.copyBaseSfromDecimal(self, self.getDecimalValue() // other.getDecimalValue()) # baseS only supports integer division
    
    def __floordiv__(self, other):
        return self.copyBaseSfromDecimal(self, self.getDecimalValue() // other.getDecimalValue())
    
    def __mod__(self, other):
        if type(other) == int:
            return self.copyBaseSfromDecimal(self, self.getDecimalValue() % other)
        return self.copyBaseSfromDecimal(self, self.getDecimalValue() % other.getDecimalValue())
    
    def __pow__(self, other):
        return self.copyBaseSfromDecimal(self, self.getDecimalValue() ** self.getDecimalValue())
    
    def __eq__(self, other):
        if type(other) == int:
            return self.getDecimalValue() == other
        return self.getDecimalValue() == other.getDecimalValue()
    
    def __ne__(self, other):
        if type(other) == int:
            return self.getDecimalValue() != other
        return self.getDecimalValue() != other.getDecimalValue()
    
    def __lt__(self, other):
        if type(other) == int:
            return self.getDecimalValue() < other
        return self.getDecimalValue() < other.getDecimalValue()
    
    def __le__(self, other):
        if type(other) == int:
            return self.getDecimalValue() <= other
        return self.getDecimalValue() <= other.getDecimalValue()
    
    def __gt__(self, other):
        if type(other) == int:
            return self.getDecimalValue() > other
        return self.getDecimalValue() > other.getDecimalValue()
    
    def __ge__(self, other):
        if type(other) == int:
            return self.getDecimalValue() >= other
        return self.getDecimalValue() >= other.getDecimalValue()
    
    def __abs__(self):
        if self.getDecimalValue() < 0:
            return self.copyBaseSfromDecimal(self, -self.getDecimalValue())
        return self
    
    def __neg__(self):
        return self.copyBaseSfromDecimal(self, -self.getDecimalValue())
    
    def __hash__(self):
        return hash(self.getDecimalValue())