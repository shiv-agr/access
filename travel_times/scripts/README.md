# Contents of this repository:
----
1. p2p - a package for computing transit matrices for very large data sets
2. ScoreModel - a tool to manage the underlying data for geospatial models
3. CommunityAnalytics - Contains two models for studying urban accessibility to nonprofit services: HSSAModel and PCSpendModel
4. SAE - "simulation and analytics engine" to optimize constrained resource allocation problems
5. CleanContractsData - a script to clean contracts data

Together, these packages run as a stack with 3 levels: p2p, CommunityAnalytics, and SAE. p2p is a dependency of CommunityAnalytics, and p2p and CommunityAnalytics are in turn both dependencies of SAE. If you are only interested in one level of the stack however (p2p or CommunityAnalytics, don't care about SAE) you can use those independently.

The package is written in Python 3.6, C++ 11 and Cython. Currently, the only supported operating systems are MacOS and Ubuntu (if you don't have either, a guide for installing Ubuntu 16.04 LTS is at the bottom of this README. )

# Installation Options

## General Installation Instructions
----
1. Clone this directory
2. Requirements: python3, pip3
3. Run `pip3 install -r requirements.txt`, also in the cloned directory.
4. If you get any errors, try running `pip3 install -r requirements.txt --upgrade`.
5. Run `python3 setup.py install` in the cloned directory (If you are on linux, throw a `sudo` in front)

## Installing from pre-loaded Ubuntu 16.04 LTS disk image

1. Download and install VirtualBox: https://www.virtualbox.org
2. Download CSDSVM.ova (currently on Box)
3. File->Import Applicance and choose the .ova
4. Select the imported image and go to Settings->System. Adjust "Base Memory" under the Motherboard tab and "processors" under the Processor tab. This will tell VirtualBox how much of your machine's resources to dedicate to the application.
5. Start the image, and navigate to contracts/analytics directory and run `bash ubuntu_easy_update.sh` (do this every time you use the software)

## Installing Ubuntu 16.04 LTS with dependencies from scratch

1. Follow the instructions at this link: https://linus.nci.nih.gov/bdge/installUbuntu.html
2. `sudo apt-get install git`
3. `git clone https://github.com/GeoDaCenter/contracts.git`
4. `sudo apt-get update`
5. `sudo apt-get upgrade`
6. `sudo add-apt-repository universe`
7. `sudo apt-get update` (yes, run this command again--it's a bug in Ubuntu 16.04 LTS)
8. `sudo apt-get -y install python3-pip`
9. `sudo apt-get install libspatialindex-dev` 
10. `sudo apt-get install python3-tk`
11. `pip3 install cython`
11. Navigate to analytics directory and run `bash ubuntu_easy_update.sh` (do this every time you use the software)


## P2P: A python package to efficiently compute the shortest path transit matrices for very large datasets.

=====

### Introduction

Generating large shortest path matrices for different transit types is an important tool for spatial data science, but does not currently have a solution that is open source, highly scalable and efficient. Several tools currently exist which fill a similar purpose to this software package. OSRM, Valhalla and Google Maps, among other services, offer matrix APIs to compute the shortest path distance for datasets but break down when appied to very large datasets.

Each of the above services caps the number of entries in a request at 25-50, meaning that generating a matrix with 500,000 rows requires breaking the original matrix into millions of submatrices and making millions of individual queries. This approach works well for small datasets, but includes substantial overhead which is prohibitive on a large scale. P2P can generate shortest path matrices between a set of source and destination points (or source-source) in 2 lines of code, efficiently and with a low memory footprint.

P2P generated a driving shortest path matrix for 46,265 blocks in Chicago in ~14 minutes (18 minutes for walking) whereas the same task took > 18 hours using MapZen's Valhalla. For this particular dataset, the mean difference between time values for the driving shortest path matrix and Google Maps' Matrix API was 2 minutes. For a demo of the workflow, see demo.ipynb.


### Usage


There are two ways to use p2p. If you have one table, you'll get a symmetric matrix of the network time from every point to every other point. If you have two tables, you'll get an asymmetric matrix mapping every point in table 1 to every point in table 2. Currently, the only supported modes of transit are `drive`, `walk` and `bike`.

This package is currently in beta, so it is not guaranteed to be 100% reliable.

p2p runs in O(Elog(V)) time, where V is the number of nodes (and E is the Edges) in the street network in your area of interest (not the number of points in your table). On a system with 2 x 2.66 GHz 6-Core Intel Xeon processors and 64 GB of memory, a table representing a walking matrix for entire city of Chicago was computed in ~16 minutes and was 6 GB. The same driving matrix took ~13 minutes to process, because walking networks typically have around 20% more nodes than driving networks.

To get accurate results for driving networks, you need to supply a speed limit table which specifies street names and speed limits (in MPH) for your area of interest. You can find this data for Chicago in resources/condensed_street_data.csv, butyou will need to supply it yourself if your data lie elsewhere.

One other parameter that you can adjust on a case-by-case basis is the epsilon value, which controls how large to make the network bounding box beyond your dataset. Larger epsilons result in longer computation times, but smaller epsilons result in slightly reduced accuracy at the very edges of the bounding box, especially for driving networks. The default is currently set at 0.05, which seems to balance the two reasonably well. (+/-) 0.02 will result in a large increase/decrease in computation time and accuracy..

There is currently one known bug which can, in large data sets, cause nodes at the very edge of the bounding box to result in traversal times of -1 (it's pretty rare, but a fix is forthcoming).

### Technical Overview

The operation of P2P can be broken down into 6 steps:

1. Determining the bounding box:

First, we extract the extreme value of latitude/longitude from the source table and increase the borders of the bounding box by 'epsilon'. This is done avoid cutting off edges leading to data points near the boundary of the bounding box. Any points from the destination table outside the bounding box are dropped.

3. Download OSM network:

Using the previously determined bounding box, I then generate a query and download the appropriate network type from OSM, which consists of nodes and edges with a distance value. This is the only point any metadata (two coordinate pairs) related to the source data leaves the local system. 

3. Costing model:

The costing model has two components: an edge traversal speed and a node penalty. If the network type is 'walk', a walk speed of 5 km/h is used with no node penalty. If the network type is 'bike', a walk speed of 15 km/h is used with no node penalty. If the network type is driving, the edge traversal speed is drawn from a table of speed limits that must be supplied separately (and a default speed limit of 40 km/h for edges that cannot be matched), and the node penaty is 0 seconds. The network is directed, meaning that one way streets are respected and A->B and B->A can have different edge traversal speeds. The sparse network generated by this step is written to file.

4. Nearest Neighbor:

P2P uses a k-d tree to match each point in the source and destination data to its nearest neighbor node in the OSM network, and then finds the Vincenty distance between the two points.

5. Dijkstra's Algorithm:

P2P uses an adjacency list representation for Dijkstra's algorithm to find the shortest path for every node to every other node in the underlying OSM network, but it can skip doing any processing for nodes that do not have an attached source data point. The advantage of this approach is that it scales to essentially any size dataset; as opposed to the adjacency matrix representation (which can easily exceed the memory of many systems for reasonably large datasets) P2P never loads the entire network into memory at one time, meaning the memory footprint is relatively small. This also means the multithreaded performance of P2P greatly outperforms the singlethreaded performance. 

6. Compute Final Impedence:

For every point in the source dataset to every point in the destination dataset, the base impedence is the cost found using Dijstra. To the base value we add the 'last mile' inferred impedence from the source and destination points to their respective nearest nodes, determined by the Euclidean distance and a constant traversal speed. The 'last mile' is figurative; in the City of Chicago, for instance, 75 percent of block centroids were within 100 meters of the nearest OSM node and 95 percent of block centroids were within 200 meters.


# Questions/Feedback?

lnoel@uchicago.edu
