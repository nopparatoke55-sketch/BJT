from bjt import BiasInput, solve_thevenin, solve_nodal, cross_check

x = BiasInput(vcc=12, r1=100000, r2=22000, rc=2200, re=1000, beta=100, vbe=0.7)
t = solve_thevenin(x)
n = solve_nodal(x)
d = cross_check(t, n)

print("Region :", t.region.upper())
print("IB A   :", t.ib)
print("IC A   :", t.ic)
print("IE A   :", t.ie)
print("VB V   :", t.vb)
print("VC V   :", t.vc)
print("VE V   :", t.ve)
print("VCE V  :", t.vce)
print("max d  :", max(d.values()))
