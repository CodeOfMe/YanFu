Q-r. Yu et al。
Geoscience Frontiers 10 (2019) 1437-1447
1445
Vectors U and
For one-dimensional vectors, this calculation is
Clustering for vertical colulns can be used to evaluate correlation
Shown in Eq: (1).
between different oxides or elements。
The colored matrix in the
middle Of Fig. Ze is a combination of the correlation matrix Of rOWs
UiVi
SuiSyi
and columns。
CC(U,v)
(1
Data in Table 10 contain different samples Of
a Same Volcanic
VSu
(Cui)' VSi
Syj)
rock. It can be seen from Fig: 2e that these samples can be divided
The Euclidean distances between each tWo Of those vectors are
into tWo groups by HCA, and
and other oxides is significantly
needed to process the HCA. Then there comes the need OfEq. (2) to
dissimilar; Which hints that there may be other sources Of in-
Calculate the distance d between the row |column vectors U and
gredients that affect the silica content。
Suivi
SuiSyi
5.4.3.
Developing functions
d(U,v)
二1 - CC(U,v)
二
Besides the routines mentioned above; new functions have been
VSI
(Sui VS}
added, including a clay-silt-sand classification diagram
Fig. 2fand
(2)
data in Table 11),a 30 visualization function (Fig. 28), and an Auto
function to generate all available Calculations and plots for im-
Briefly speaking; the correlation matrix is calculated frstly, with
ported data. GeoPyTool is still in development, more functions Will
which the distance matrix can be calculated and used for the HCA
be gradually added。
Process. It is clear that HCA function needs to perform matrix cal-
culations, So there are mathematically limitations. If there are any
blank items in the data, Or 讦 the data matrix is
Singular matrix;
HCA won't be possible。
5.5.
Output fles
At
the
code level;
this program
USeS
Scipy to complete the
Calculation process (Oliphant, 2007 ). This article only describes the
GeoPyTool generates MS Excel XLSX and CSV fles as output files
main idea instead Of the specific calculation process, Which can be
containing calculation result and generates diagrams in a PNG, SVG
Seen
讧
code;
at
https: Ilgithub.comlGeoPyToollGeoPyToollblob/
O[
PDF format。
The
PNG
format
has become
ah
International
masterlgeopytoollClusterpy
Standard (ISOIIEC 15948:2003 ) and Was classified as a World Wide
Specifically, take Table 10 as an example; i Which horizontal
Web Consortiur (W3C) recommendation in 2003 (Suyanto, 2008;
TOWS and Vertical colurns are respectively considered as compar
Web,
2010)。
This
formnat
ls
also supported by
all
mainstream
ative indexes. Each Iow is considered as a one-dimensional vector。
operating systems and provides images with a decent quality. The
Euclidean distances between each tWO IOWS is used for the Clus-
SVG format is
Widely deployed royalty-free graphic format
tering Of left dendrogram shown in Fig: 2e. Similar process for each
developed and maintained by the W3C SVC Working Group. It is
column generates the dendrogram in the upper part of Fig: Ze. The
supported by all modern browsers
both desktop and mobile
left dendrogram and the clustering for horizontal rows can be used
computers (Quint; 2003 ). The PDE format is also widely used as
t0 separate ungrouped data into several groups, Or to estimate the
universal format for documents and is used in GeoPyTool as
dissimilarity Of different
TOWs. The upper dendrogram
and
the
complementary and extra format to SVG
Major
Prograls
Table 11
Sand-silt-clay data (vol %) sample for GeoPyTool。
Label
Marker
Color
Size
Alpha
Style
Width
Clay
Sand
Silt
First Group
green
50
0.6
0.4
60.0
25.0
15.0
green
50
0.6
0.4
44.0
31.0
25.0
50
0.4
62.6
18.7
18
50
67.7
9.0
23.3
50
66.6
21.8
11.6
50
0.4
67.5
18.8
13
50
0.4
59.5
20.5
20
green
50
0.4
69.8
15.2
15
green
50
0.5
59.8
15.2
25
green
50
0.5
62.6
18.7
18
green
50
0.5
61.3
16.8
21.9
green
50
0.5
58.3
20
21.7
50
0.5
66
13.0
20.3
50
0.5
51.5
30.5
18.0
50
1.5
74.3
11.4
14.3
Second Group
blue
50
2.5
50.0
35.0
15.0
blue
50
3.5
54.4
18.4
27.2
blue
50
80.3
11.8
7.9
&
blue
50
51.3
27.1
21.6
blue
50
56.4
28.3
15.3
Third Group
grey
50
58.3
20.0
21.7
grey
50
66.7
18.0
15.3
D
D
grey
50
#
76.0
13.9
120
grey
50
70.0
17.5
12.5
D
grey
50
69.8
11.0
19.2
The Last Group
red
50
51.8
48.2
red
50
40.8
59.2
red
50
1.5
61.0
39.0
red
50
0.6
2.5
40.0
60.0
SiO2
for
graphic
green
green
green
green
green
green
green
green