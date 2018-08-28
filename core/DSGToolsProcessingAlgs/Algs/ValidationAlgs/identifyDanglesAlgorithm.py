# -*- coding: utf-8 -*-
"""
/***************************************************************************
 DsgTools
                                 A QGIS plugin
 Brazilian Army Cartographic Production Tools
                              -------------------
        begin                : 2018-08-13
        git sha              : $Format:%H$
        copyright            : (C) 2018 by Philipe Borba - Cartographic Engineer @ Brazilian Army
        email                : borba.philipe@eb.mil.br
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from DsgTools.core.GeometricTools.layerHandler import LayerHandler
from .validationAlgorithm import ValidationAlgorithm
import processing
from PyQt5.QtCore import QCoreApplication
from qgis.core import (QgsProcessing,
                       QgsFeatureSink,
                       QgsProcessingAlgorithm,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterFeatureSink,
                       QgsFeature,
                       QgsDataSourceUri,
                       QgsProcessingOutputVectorLayer,
                       QgsProcessingParameterVectorLayer,
                       QgsWkbTypes,
                       QgsProcessingParameterBoolean,
                       QgsProcessingParameterEnum,
                       QgsProcessingParameterNumber,
                       QgsProcessingParameterMultipleLayers,
                       QgsProcessingUtils,
                       QgsSpatialIndex,
                       QgsGeometry)

class IdentifyDanglesAlgorithm(ValidationAlgorithm):
    INPUT = 'INPUT'
    SELECTED = 'SELECTED'
    TOLERANCE = 'TOLERANCE'
    LINEFILTERLAYERS = 'LINEFILTERLAYERS'
    POLYGONFILTERLAYERS = 'POLYGONFILTERLAYERS'
    TYPE = 'TYPE'
    IGNOREINNER = 'IGNOREINNER'
    FLAGS = 'FLAGS'
    

    def initAlgorithm(self, config):
        """
        Parameter setting.
        """
        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.INPUT,
                self.tr('Input layer'),
                [QgsProcessing.TypeVectorLine ]
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.SELECTED,
                self.tr('Process only selected features')
            )
        )
        self.addParameter(
            QgsProcessingParameterNumber(
                self.TOLERANCE,
                self.tr('Search radius'),
                minValue=0,
                defaultValue=2
            )
        )
        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                self.LINEFILTERLAYERS,
                self.tr('Linestring Filter Layers'),
                QgsProcessing.TypeVectorLine,
                optional = True
            )
        )
        self.addParameter(
            QgsProcessingParameterMultipleLayers(
                self.POLYGONFILTERLAYERS,
                self.tr('Polygon Filter Layers'),
                QgsProcessing.TypeVectorPolygon,
                optional = True
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.TYPE,
                self.tr('Ignore dangle on unsegmented lines')
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.IGNOREINNER,
                self.tr('Ignore search radius on inner layer search')
            )
        )
        self.addParameter(
            QgsProcessingParameterFeatureSink(
                self.FLAGS,
                self.tr('{0} Flags').format(self.displayName())
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        """
        Here is where the processing itself takes place.
        """

        inputLyr = self.parameterAsVectorLayer(parameters, self.INPUT, context)
        onlySelected = self.parameterAsBool(parameters, self.SELECTED, context)
        searchRadius = self.parameterAsDouble(parameters, self.TOLERANCE, context)
        lineFilterLyrList = self.parameterAsLayerList(parameters, self.LINEFILTERLAYERS, context)
        polygonFilterLyrList = self.parameterAsLayerList(parameters, self.POLYGONFILTERLAYERS, context)
        ignoreNotSplit = self.parameterAsBool(parameters, self.TYPE, context)
        ignoreInner = self.parameterAsBool(parameters, self.IGNOREINNER, context)
        self.prepareFlagSink(parameters, inputLyr, QgsWkbTypes.Point, context)

        # Compute the number of steps to display within the progress bar and
        # get features from source
        featureList, total = self.getIteratorAndFeatureCount(inputLyr)
        endVerticesDict = self.buildInitialAndEndPointDict(featureList, 0.25*total, feedback)
        #search for dangles candidates
        pointList = self.searchDanglesOnPointDict(endVerticesDict, feedback, progressDelta=25)
        #build filter layer
        filterLayer = self.buildFilterLayer(lineFilterLyrList, polygonFilterLyrList, context, feedback, onlySelected=onlySelected)
        delta = 20 if not ignoreInner else 40
        #filter pointList with filterLayer
        if filterLayer:
            filteredPointList = self.filterPointListWithFilterLayer(pointList, filterLayer, searchRadius, feedback, progressDelta = delta)
        else:
            filteredPointList = pointList
            feedback.setProgress(feedback.progress()+delta)
        #filter with own layer
        if not ignoreInner: #True when looking for dangles on contour lines
            filteredPointList = self.filterPointListWithFilterLayer(filteredPointList, inputLyr, searchRadius, feedback, isRefLyr = True, ignoreNotSplit = ignoreNotSplit, progressDelta=20)
        #build flag list with filtered points
        if filteredPointList:
            currentValue = feedback.progress()
            currentTotal = 10/len(filteredPointList)
            for current, point in enumerate(filteredPointList):
                if feedback.isCanceled():
                    break
                self.flagFeature(QgsGeometry.fromPointXY(point), self.tr('Dangle on {0}').format(inputLyr.name()))
                feedback.setProgress(currentValue + int(current*currentTotal))      
        feedback.setProgress(100)
        return {self.FLAGS: self.flag_id}

    def buildInitialAndEndPointDict(self, featureList, total, feedback, progressDelta = 100):
        """
        Calculates initial point and end point from each line from lyr.
        """
        # start and end points dict
        currentProgress = feedback.progress()
        endVerticesDict = dict()
        localTotal = total
        # iterating over features to store start and end points
        for current, feat in enumerate(featureList):
            if feedback.isCanceled():
                break
            geom = feat.geometry()
            lineList = geom.asMultiPolyline() if geom.isMultipart() else [geom.asPolyline()]
            for line in lineList:
                self.addFeatToDict(endVerticesDict, line, feat.id())
            feedback.setProgress(currentProgress + int(localTotal*current))
        return endVerticesDict

    def addFeatToDict(self, endVerticesDict, line, featid):
        self.addPointToDict(line[0], endVerticesDict, featid)
        self.addPointToDict(line[len(line) - 1], endVerticesDict, featid)
    
    def addPointToDict(self, point, pointDict, featid):
        if point not in pointDict:
            pointDict[point] = []
        pointDict[point].append(featid)
    
    def searchDanglesOnPointDict(self, endVerticesDict, feedback, progressDelta = 100):
        """
        Counts the number of points on each endVerticesDict's key and returns a list of QgsPoint built from key candidate.
        """
        pointList = []
        currentProgress = feedback.progress()
        localTotal = progressDelta/len(endVerticesDict)
        # actual search for dangles
        for current, point in enumerate(endVerticesDict):
            if feedback.isCanceled():
                break
            # this means we only have one occurrence of point, therefore it is a dangle
            if len(endVerticesDict[point]) <= 1:
                pointList.append(point)
            feedback.setProgress(currentProgress + int(localTotal*current))
        return pointList

    def buildFilterLayer(self, lineLyrList, polygonLyrList, context, feedback, onlySelected = False):
        """
        Buils one layer of filter lines.
        Build unified layer is not used because we do not care for attributes here, only geometry.
        refLyr elements are also added.
        """
        if not(lineLyrList + polygonLyrList):
            return []
        layerHandler = LayerHandler()
        lineLyrs = lineLyrList
        for polygonLyr in polygonLyrList:
            if feedback.isCanceled():
                break
            lineLyrs += [self.makeBoundaries(polygonLyr, context, feedback)]
        if not lineLyrs:
            return None
        unifiedLinesLyr = layerHandler.createAndPopulateUnifiedVectorLayer(lineLyrs, QgsWkbTypes.MultiLineString, onlySelected = onlySelected)
        filterLyr = self.cleanLayer(unifiedLinesLyr, [0,6], context)
        return filterLyr
    
    def makeBoundaries(self, lyr, context, feedback):
        parameters = {
            'INPUT' : lyr,
            'OUTPUT' : 'memory:'
        }
        output = processing.run("native:boundary", parameters, context = context)
        return output['OUTPUT']

    def cleanLayer(self, inputLyr, toolList, context, typeList=[0,1,2,3,4,5,6]): 
        #TODO write one class that runs all processing stuff (model that tomorrow)
        output = QgsProcessingUtils.generateTempFilename('output.shp')
        error = QgsProcessingUtils.generateTempFilename('error.shp')
        parameters = {
            'input':inputLyr,
            'type':typeList,
            'tool':toolList,
            'threshold':'-1', 
            '-b':False, 
            '-c':True, 
            'output' : output, 
            'error': error, 
            'GRASS_REGION_PARAMETER':None,
            'GRASS_SNAP_TOLERANCE_PARAMETER': -1,
            'GRASS_MIN_AREA_PARAMETER': 0.0001,
            'GRASS_OUTPUT_TYPE_PARAMETER': 0,
            'GRASS_VECTOR_DSCO':'',
            'GRASS_VECTOR_LCO':''
            }
        x = processing.run('grass7:v.clean', parameters, context = context)
        lyr = QgsProcessingUtils.mapLayerFromString(x['output'], context)
        return lyr

    def filterPointListWithFilterLayer(self, pointList, filterLayer, searchRadius, feedback, progressDelta = 100, isRefLyr = False, ignoreNotSplit = False):
        """
        Builds buffer areas from each point and evaluates the intersecting lines. If there are more than two intersections, it is a dangle.
        """
        currentProgress = feedback.progress()
        localTotal = progressDelta/len(pointList)
        spatialIdx, allFeatureDict = self.buildSpatialIndexAndIdDict(filterLayer)
        notDangleList = []
        for current, point in enumerate(pointList):
            if feedback.isCanceled():
                break
            candidateCount = 0
            qgisPoint = QgsGeometry.fromPointXY(point)
            #search radius to narrow down candidates
            buffer = qgisPoint.buffer(searchRadius, -1)
            bufferBB = buffer.boundingBox()
            #gets candidates from spatial index
            candidateIds = spatialIdx.intersects(bufferBB)
            #if there is only one feat in candidateIds, that means that it is not a dangle
            bufferCount = len([id for id in candidateIds if buffer.intersects(allFeatureDict[id].geometry())])
            for id in candidateIds:
                if not isRefLyr:
                    if buffer.intersects(allFeatureDict[id].geometry()) and \
                    qgisPoint.distance(allFeatureDict[id].geometry()) < 10**-9: #float problem, tried with intersects and touches and did not get results
                        notDangleList.append(point)
                        break
                else:
                    if ignoreNotSplit:
                        if buffer.intersects(allFeatureDict[id].geometry()) and \
                        (qgisPoint.distance(allFeatureDict[id].geometry()) < 10**-9 or \
                        qgisPoint.intersects(allFeatureDict[id].geometry())): #float problem, tried with intersects and touches and did not get results
                            candidateCount += 1
                    else:
                        if buffer.intersects(allFeatureDict[id].geometry()) and \
                        (qgisPoint.touches(allFeatureDict[id].geometry())): #float problem, tried with intersects and touches and did not get results
                            candidateCount += 1
                    if candidateCount == bufferCount:
                        notDangleList.append(point)
            feedback.setProgress(currentProgress + localTotal*current)
        filteredDangleList = [point for point in pointList if point not in notDangleList]
        return filteredDangleList
    
    def buildSpatialIndexAndIdDict(self, inputLyr):
        """
        creates a spatial index for the centroid layer
        """
        spatialIdx = QgsSpatialIndex()
        idDict = {}
        for feat in inputLyr.getFeatures():
            spatialIdx.insertFeature(feat)
            idDict[feat.id()] = feat
        return spatialIdx, idDict

    def name(self):
        """
        Returns the algorithm name, used for identifying the algorithm. This
        string should be fixed for the algorithm, and must not be localised.
        The name should be unique within each provider. Names should contain
        lowercase alphanumeric characters only and no spaces or other
        formatting characters.
        """
        return 'identifydangles'

    def displayName(self):
        """
        Returns the translated algorithm name, which should be used for any
        user-visible display of the algorithm name.
        """
        return self.tr('Identify Dangles')

    def group(self):
        """
        Returns the name of the group this algorithm belongs to. This string
        should be localised.
        """
        return self.tr('Validation Tools (Identification Processes)')

    def groupId(self):
        """
        Returns the unique ID of the group this algorithm belongs to. This
        string should be fixed for the algorithm, and must not be localised.
        The group id should be unique within each provider. Group id should
        contain lowercase alphanumeric characters only and no spaces or other
        formatting characters.
        """
        return 'DSGTools: Validation Tools (Identification Processes)'

    def tr(self, string):
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return IdentifyDanglesAlgorithm()