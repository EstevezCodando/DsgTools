# -*- coding: utf-8 -*-
"""
/***************************************************************************
 DsgTools
                                 A QGIS plugin
 Brazilian Army Cartographic Production Tools
                              -------------------
        begin                : 2023-08-01
        git sha              : $Format:%H$
        copyright            : (C) 2023 by Philipe Borba - Cartographic Engineer @ Brazilian Army
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

from abc import abstractclassmethod
from collections import defaultdict
import copy
import json
from typing import Any, Dict, Iterable, List, Union, Optional
from qgis.core import (
    QgsFeature,
    QgsVectorLayer,
    QgsFeedback,
    QgsProcessingMultiStepFeedback,
    QgsVectorLayerUtils,
    QgsWkbTypes,
    NULL,
)

from DsgTools.core.GeometricTools.geometryHandler import GeometryHandler


class AbstractFeatureProcessor:
    def __init__(self):
        self.geometryHandler = GeometryHandler()

    def deaggregateGeometries(self, featDict, parameterDict):
        geomList = self.geometryHandler.handleGeometry(
            featDict["geom"], parameterDict=parameterDict
        )
        featDictWithoutNULL = dict()
        for k, v in featDict.items():
            featDictWithoutNULL[k] = v if v != NULL else None
        if len(geomList) == 1:
            features = [featDictWithoutNULL]
        else:
            features = []
            featDictWithoutNULL.pop("geom")
            for geom in geomList:
                copyDict = copy.deepcopy(featDictWithoutNULL)
                copyDict["geom"] = geom
                features.append(copyDict)
        return features

    def convert(self, featDictList, parameterDict, feedback=None):
        outputFeatDictList = []
        if feedback is not None:
            nFeats = len(featDictList)
            if nFeats == 0:
                return []
            stepSize = 100 / nFeats
        for current, featDict in enumerate(featDictList):
            if feedback is not None and feedback.isCanceled():
                return outputFeatDictList
            outputFeatDictList += self.convert_feat(featDict, parameterDict)
            if feedback is not None:
                feedback.setProgress(current * stepSize)
        return outputFeatDictList

    @abstractclassmethod
    def convert_feat(self, featDict):
        pass


class FeatureProcessor(AbstractFeatureProcessor):
    def convert_feat(self, featDict, parameterDict):
        return self.deaggregateGeometries(featDict, parameterDict)


class MappingFeatureProcessor(AbstractFeatureProcessor):
    def __init__(self, mappingDictPath: str, mappingType: str):
        self.mappingDict = self.buildFileDict(mappingDictPath)
        self.mappingType = mappingType
        self.geometryHandler = GeometryHandler()

    def buildFileDict(self, mappingPath):
        with open(mappingPath, "r", encoding="utf-8") as file:
            mapDict = json.loads(file.read())
        return mapDict

    def buildFeatureDict(self, feature):
        featDict = dict()
        for attr in feature.getAllAttributeNames():
            if attr == "layer_name" or (
                "multi_writer" not in attr
                and "multi_reader_" not in attr
                and "fme_" not in attr
                and "postgis_" not in attr
            ):
                if feature.getAttribute(attr) or feature.getAttribute(attr) == 0:
                    if feature.getAttribute(attr) == "f":
                        featDict[attr] = "False"
                    elif feature.getAttribute(attr) == "t":
                        featDict[attr] = "True"
                    else:
                        featDict[attr] = feature.getAttribute(attr)
                else:
                    featDict[attr] = None
        if (
            feature.performFunction("@GeometryType()") == "fme_polygon"
            or feature.performFunction("@GeometryType()") == "fme_donut"
        ):
            featDict["$GEOM_TYPE"] = "POLYGON"
        elif feature.performFunction("@GeometryType()") == "fme_line":
            featDict["$GEOM_TYPE"] = "LINESTRING"
        elif feature.performFunction("@GeometryType()") == "fme_point":
            featDict["$GEOM_TYPE"] = "POINT"
        else:
            featDict["INVALID_GEOM"] = True
        return featDict

    def evaluateExpression(self, featDict, expression):
        if not expression["nome_atributo"] in featDict:
            return False
        if expression["valor"] is None or expression["valor"] == "":
            return (
                featDict[expression["nome_atributo"]] is None
                or featDict[expression["nome_atributo"]] == ""
            )
        else:
            return "{0}".format(featDict[expression["nome_atributo"]]) == "{0}".format(
                expression["valor"]
            )

    def evaluateFilter(self, featDict, filter_condition):
        if "$and" in filter_condition:
            return all(
                [
                    self.evaluateFilter(featDict, condition)
                    for condition in filter_condition["$and"]
                ]
            )
        elif "$or" in filter_condition:
            return any(
                [
                    self.evaluateFilter(featDict, condition)
                    for condition in filter_condition["$or"]
                ]
            )
        elif "$not" in filter_condition:
            return not self.evaluateFilter(featDict, filter_condition["$not"])
        else:
            return self.evaluateExpression(featDict, filter_condition)

    def convertFeature(self, featDict):
        if self.mappingType == "ida":
            key_attr_origin = "attr_ida"
            key_attr_destiny = "attr_volta"
            key_value_origin = "valor_ida"
            key_value_destiny = "valor_volta"
            key_default = "atributos_default_ida"
            key_filter = "filtro_ida"
            key_class_origin = "classe_ida"
            key_class_destiny = "classe_volta"
            key_group_origin = "tupla_ida"
            key_group_destiny = "tupla_volta"
            key_affix_origin = "afixo_geom_ida"
            key_affix_destiny = "afixo_geom_volta"
            key_schema_origin = "schema_ida"
            key_schema_destiny = "schema_volta"
            key_class_affix_origin = "com_afixo_geom_ida"
            key_class_affix_destiny = "com_afixo_geom_volta"
            key_class_schema_origin = "com_schema_ida"
            key_class_schema_destiny = "com_schema_volta"
            key_agregar = "agregar_geom_ida"
        else:
            key_attr_origin = "attr_volta"
            key_attr_destiny = "attr_ida"
            key_value_origin = "valor_volta"
            key_value_destiny = "valor_ida"
            key_default = "atributos_default_volta"
            key_filter = "filtro_volta"
            key_class_origin = "classe_volta"
            key_class_destiny = "classe_ida"
            key_group_origin = "tupla_volta"
            key_group_destiny = "tupla_ida"
            key_affix_origin = "afixo_geom_volta"
            key_affix_destiny = "afixo_geom_ida"
            key_schema_origin = "schema_volta"
            key_schema_destiny = "schema_ida"
            key_class_affix_origin = "com_afixo_geom_volta"
            key_class_affix_destiny = "com_afixo_geom_ida"
            key_class_schema_origin = "com_schema_volta"
            key_class_schema_destiny = "com_schema_ida"
            key_agregar = "agregar_geom_volta"

        featDict["layer_name_original"] = featDict["layer_name"]

        if (
            key_schema_origin in self.mappingDict
            and self.mappingDict[key_schema_origin]
        ):
            featDict["layer_name"] = featDict["layer_name"][
                len(self.mappingDict[key_schema_origin]) + 1 :
            ]

        featDict["layer_name_sem_schema"] = featDict["layer_name"]

        if (
            key_affix_origin in self.mappingDict
            and "tipo" in self.mappingDict[key_affix_origin]
            and self.mappingDict[key_affix_origin]["tipo"] == "sufixo"
        ):
            featDict["layer_name"] = featDict["layer_name"][
                : -len(self.mappingDict[key_affix_origin][featDict["$GEOM_TYPE"]])
            ]
            featDict["layer_name_sem_afixo"] = featDict["layer_name_original"][
                : -len(self.mappingDict[key_affix_origin][featDict["$GEOM_TYPE"]])
            ]

        if (
            key_affix_origin in self.mappingDict
            and "tipo" in self.mappingDict[key_affix_origin]
            and self.mappingDict[key_affix_origin]["tipo"] == "prefixo"
        ):
            featDict["layer_name"] = featDict["layer_name"][
                len(self.mappingDict[key_affix_origin][featDict["$GEOM_TYPE"]]) :
            ]
            featDict["layer_name_sem_afixo"] = featDict["layer_name_original"][
                len(self.mappingDict[key_affix_origin][featDict["$GEOM_TYPE"]]) :
            ]

        should_map = False
        for classmap in self.mappingDict["mapeamento_classes"]:
            if not (
                "sentido" not in classmap
                or ("sentido" in classmap and classmap["sentido"] == self.mappingType)
            ):
                continue
            if (
                key_class_affix_origin in classmap
                and classmap[key_class_affix_origin]
                and key_class_schema_origin in classmap
                and classmap[key_class_schema_origin]
            ):
                class_name = featDict["layer_name_original"]
            elif (
                key_class_affix_origin in classmap and classmap[key_class_affix_origin]
            ):
                class_name = featDict["layer_name_sem_schema"]
            elif (
                key_class_schema_origin in classmap
                and classmap[key_class_schema_origin]
            ):
                class_name = featDict["layer_name_sem_afixo"]
            else:
                class_name = featDict["layer_name"]

            if classmap[key_class_origin] == class_name:
                if key_filter in classmap:
                    if not self.evaluateFilter(featDict, classmap[key_filter]):
                        continue
                should_map = True
        if not should_map:
            featDict["CLASS_NOT_FOUND"] = True
            return featDict

        mappedFeat = copy.deepcopy(featDict)

        if key_default in self.mappingDict:
            for default in self.mappingDict[key_default]:
                mappedFeat[default["nome_atributo"]] = default["valor"]

        if "mapeamento_atributos" in self.mappingDict:
            self.map_attributes(
                featDict,
                key_attr_origin,
                key_attr_destiny,
                key_value_origin,
                key_value_destiny,
                mappedFeat,
            )

        if "mapeamento_multiplo" in self.mappingDict:
            self.multiple_mapping(
                featDict, key_group_origin, key_group_destiny, mappedFeat
            )

        if "mapeamento_classes" in self.mappingDict:
            self.class_mapping(
                featDict,
                key_attr_origin,
                key_attr_destiny,
                key_value_origin,
                key_value_destiny,
                key_default,
                key_filter,
                key_class_origin,
                key_class_destiny,
                key_group_origin,
                key_group_destiny,
                key_affix_destiny,
                key_schema_destiny,
                key_class_affix_origin,
                key_class_affix_destiny,
                key_class_schema_origin,
                key_class_schema_destiny,
                key_agregar,
                mappedFeat,
            )

        return mappedFeat

    def class_mapping(
        self,
        featDict,
        key_attr_origin,
        key_attr_destiny,
        key_value_origin,
        key_value_destiny,
        key_default,
        key_filter,
        key_class_origin,
        key_class_destiny,
        key_group_origin,
        key_group_destiny,
        key_affix_destiny,
        key_schema_destiny,
        key_class_affix_origin,
        key_class_affix_destiny,
        key_class_schema_origin,
        key_class_schema_destiny,
        key_agregar,
        mappedFeat,
    ):
        for classmap in self.mappingDict["mapeamento_classes"]:
            if not (
                "sentido" not in classmap
                or ("sentido" in classmap and classmap["sentido"] == self.mappingType)
            ):
                continue
            if (
                key_class_affix_origin in classmap
                and classmap[key_class_affix_origin]
                and key_class_schema_origin in classmap
                and classmap[key_class_schema_origin]
            ):
                class_name = featDict["layer_name_original"]
            elif (
                key_class_affix_origin in classmap and classmap[key_class_affix_origin]
            ):
                class_name = featDict["layer_name_sem_schema"]
            elif (
                key_class_schema_origin in classmap
                and classmap[key_class_schema_origin]
            ):
                class_name = featDict["layer_name_sem_afixo"]
            else:
                class_name = featDict["layer_name"]

            if classmap[key_class_origin] != class_name:
                continue
            if key_filter in classmap and not self.evaluateFilter(
                featDict, classmap[key_filter]
            ):
                continue

            mappedFeat["layer_name"] = classmap[key_class_destiny]

            if (
                key_class_affix_destiny in classmap
                and classmap[key_class_affix_destiny]
            ):
                pass
            elif (
                key_affix_destiny in self.mappingDict
                and "tipo" in self.mappingDict[key_affix_destiny]
            ):
                if self.mappingDict[key_affix_destiny]["tipo"] == "sufixo":
                    mappedFeat["layer_name"] = (
                        mappedFeat["layer_name"]
                        + self.mappingDict[key_affix_destiny][featDict["$GEOM_TYPE"]]
                    )

                if self.mappingDict[key_affix_destiny]["tipo"] == "prefixo":
                    mappedFeat["layer_name"] = (
                        self.mappingDict[key_affix_destiny][featDict["$GEOM_TYPE"]]
                        + mappedFeat["layer_name"]
                    )

            if (
                key_class_schema_destiny in classmap
                and classmap[key_class_schema_destiny]
            ):
                pass
            elif (
                key_schema_destiny in self.mappingDict
                and self.mappingDict[key_schema_destiny]
            ):
                mappedFeat["layer_name"] = (
                    self.mappingDict[key_schema_destiny]
                    + "."
                    + mappedFeat["layer_name"]
                )

            if key_default in classmap:
                for default in classmap[key_default]:
                    mappedFeat[default["nome_atributo"]] = default["valor"]

            if "mapeamento_atributos" in classmap:
                for attmap in classmap["mapeamento_atributos"]:
                    if attmap[key_attr_origin] not in featDict:
                        continue
                    if attmap[key_attr_destiny] not in mappedFeat:
                        mappedFeat[attmap[key_attr_destiny]] = featDict[
                            attmap[key_attr_origin]
                        ]
                    if "traducao" not in attmap:
                        continue
                    for valuemap in attmap["traducao"]:
                        if "{0}".format(valuemap[key_value_origin]) != "{0}".format(
                            featDict[attmap[key_attr_origin]]
                        ) and (
                            "sentido" not in valuemap
                            or (
                                "sentido" in valuemap
                                and valuemap["sentido"] == self.mappingType
                            )
                        ):
                            continue
                        mappedFeat[attmap[key_attr_destiny]] = valuemap[
                            key_value_destiny
                        ]

            if "mapeamento_multiplo" in classmap:
                for attmap in classmap["mapeamento_multiplo"]:
                    if not (
                        "sentido" not in attmap
                        or (
                            "sentido" in attmap
                            and attmap["sentido"] == self.mappingType
                        )
                    ):
                        continue
                    if not all(
                        [
                            self.evaluateExpression(featDict, condition)
                            for condition in attmap[key_group_origin]
                        ]
                    ):
                        continue
                    for valuemap in attmap[key_group_destiny]:
                        if (
                            "concatenar" in valuemap
                            and valuemap["concatenar"]
                            and valuemap["nome_atributo"] in mappedFeat
                            and mappedFeat[valuemap["nome_atributo"]]
                        ):
                            mappedFeat[valuemap["nome_atributo"]] = (
                                mappedFeat[valuemap["nome_atributo"]]
                                + " | "
                                + valuemap["valor"]
                            )
                        else:
                            mappedFeat[valuemap["nome_atributo"]] = valuemap["valor"]

            if key_agregar in classmap:
                mappedFeat["AGGREGATE_GEOM"] = classmap[key_agregar]
            elif key_agregar in self.mappingDict:
                mappedFeat["AGGREGATE_GEOM"] = self.mappingDict[key_agregar]
            break

    def multiple_mapping(
        self, featDict, key_group_origin, key_group_destiny, mappedFeat
    ):
        for attmap in self.mappingDict["mapeamento_multiplo"]:
            if not (
                "sentido" not in attmap
                or ("sentido" in attmap and attmap["sentido"] == self.mappingType)
            ):
                continue
            if not all(
                [
                    self.evaluateExpression(featDict, condition)
                    for condition in attmap[key_group_origin]
                ]
            ):
                continue
            for valuemap in attmap[key_group_destiny]:
                if (
                    "concatenar" in valuemap
                    and valuemap["concatenar"]
                    and valuemap["nome_atributo"] in mappedFeat
                    and mappedFeat[valuemap["nome_atributo"]]
                ):
                    mappedFeat[valuemap["nome_atributo"]] = (
                        mappedFeat[valuemap["nome_atributo"]]
                        + " | "
                        + valuemap["valor"]
                    )
                else:
                    mappedFeat[valuemap["nome_atributo"]] = valuemap["valor"]

    def map_attributes(
        self,
        featDict,
        key_attr_origin,
        key_attr_destiny,
        key_value_origin,
        key_value_destiny,
        mappedFeat,
    ):
        for attmap in self.mappingDict["mapeamento_atributos"]:
            if attmap[key_attr_origin] not in mappedFeat:
                continue
            mappedFeat[attmap[key_attr_destiny]] = featDict[attmap[key_attr_origin]]
            if "traducao" not in attmap:
                continue
            for valuemap in attmap["traducao"]:
                if "{0}".format(valuemap[key_value_origin]) != "{0}".format(
                    featDict[attmap[key_attr_origin]]
                ) and (
                    "sentido" not in valuemap
                    or (
                        "sentido" in valuemap
                        and valuemap["sentido"] == self.mappingType
                    )
                ):
                    continue
                mappedFeat[attmap[key_attr_destiny]] = valuemap[key_value_destiny]

    def mapDictToFeature(self, feat, featDict):
        for attr, value in featDict.items():
            if value == "True":
                feat.setAttribute(attr, 1)
            elif value == "False":
                feat.setAttribute(attr, 0)
            elif value or value == 0:
                feat.setAttribute(attr, "{0}".format(value))
            else:
                feat.setAttributeNullWithType(attr, 0)
        if "AGGREGATE_GEOM" in featDict and featDict["AGGREGATE_GEOM"]:
            feat.buildAggregateFeat([feat])
        return feat

    def convert_feat(self, featDict, parameterDict):
        outputList = []
        features = self.deaggregateGeometries(featDict, parameterDict)
        for simple_feature in features:
            feat = self.buildFeatureDict(simple_feature)
            if "INVALID_GEOM" in feat and feat["INVALID_GEOM"]:
                simple_feature["INVALID_GEOM"] = True
                outputList.append(simple_feature)
                continue
            outputFeatDict = self.convertFeature(feat)
            if (
                "CLASS_NOT_FOUND" in outputFeatDict
                and not outputFeatDict["CLASS_NOT_FOUND"]
            ):
                simple_feature["CLASS_NOT_FOUND"] = True
                outputList.append(simple_feature)
            else:
                outputFeature = self.mapDictToFeature(simple_feature, outputFeatDict)
                outputList.append(outputFeature)
        return outputList


def convert_features(
    inputLayerDict: Dict[str, QgsVectorLayer],
    featureProcessor: AbstractFeatureProcessor,
    feedback: Optional[QgsFeedback] = None,
    layerNameAttr: Optional[str] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    outputFeatDict = defaultdict(list)
    multiStepFeedback = (
        QgsProcessingMultiStepFeedback(len(inputLayerDict), feedback)
        if feedback is not None
        else None
    )
    for currentLyrIdx, (inputLyrName, lyr) in enumerate(inputLayerDict.items()):
        if multiStepFeedback is not None:
            multiStepFeedback.setCurrentStep(currentLyrIdx)
            if multiStepFeedback.isCanceled():
                break
        get_feat_lambda = (
            lambda x: get_feat_dict(inputLyrName=inputLyrName, feat=x)
            if layerNameAttr is None
            else get_feat_dict(x[layerNameAttr], x)
        )
        outputFeatListDict: List[Dict[str, Any]] = featureProcessor.convert(
            list(map(get_feat_lambda, lyr.getFeatures())),
            parameterDict={"isMulti": QgsWkbTypes.isMultiType(lyr.wkbType())},
            feedback=multiStepFeedback,
        )
        for featDict in outputFeatListDict:
            outputFeatDict[featDict["layer_name"]].append(featDict)
    return outputFeatDict


def get_feat_dict(inputLyrName, feat):
    attrDict = feat.attributeMap()
    attrDict["layer_name"] = inputLyrName
    attrDict["geom"] = feat.geometry()
    return attrDict


def get_output_feature(
    inputDictMap: Dict[str, Any], destinationLayer: QgsVectorLayer
) -> QgsFeature:
    geom = inputDictMap.pop("geom")
    newFeature = QgsVectorLayerUtils.createFeature(
        layer=destinationLayer,
        geometry=geom,
    )
    pkIndexList = destinationLayer.primaryKeyAttributes()
    for idx, field in enumerate(newFeature.fields()):
        fieldName = field.name()
        if fieldName not in inputDictMap or idx in pkIndexList:
            continue
        value = inputDictMap[fieldName]
        newFeature[fieldName] = value if value is not None else NULL
    return newFeature


def write_output_features(
    featDict: Dict[str, List[Dict[str, Any]]],
    outputLayerDict: Dict[str, QgsVectorLayer],
    feedback: Optional[QgsFeedback] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    notConvertedDict = defaultdict(lambda: defaultdict(list))
    multiStepFeedback = (
        QgsProcessingMultiStepFeedback(len(featDict), feedback)
        if feedback is not None
        else None
    )
    for currentLyrIdx, (lyrName, featDictList) in enumerate(featDict.items()):
        if multiStepFeedback is not None:
            multiStepFeedback.setCurrentStep(currentLyrIdx)
            if multiStepFeedback.isCanceled():
                break
        outputLayer = outputLayerDict.get(lyrName, None)
        if outputLayer is None:
            for featDict in featDictList:
                notConvertedDict[featDict["geom"].wkbType()].append(featDict)
            continue
        get_output_feature_lambda = lambda x: get_output_feature(x, outputLayer)
        outputLayer.startEditing()
        outputLayer.beginEditCommand(f"Writing converted features on layer {lyrName}.")
        outputLayer.addFeatures(list(map(get_output_feature_lambda, featDictList)))
        outputLayer.endEditCommand()
    return notConvertedDict