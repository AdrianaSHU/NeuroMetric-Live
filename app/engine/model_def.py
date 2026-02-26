import torch
import torch.nn as nn



class EEGNet(nn.Module):
    """
    EEGNet: A Compact Convolutional Neural Network for EEG-based Brain-Computer Interfaces.
    Highly optimized for Edge AI computing (like the Raspberry Pi). It uses Depthwise 
    and Separable Convolutions to drastically reduce the number of parameters while 
    maximizing feature extraction from raw neuro-telemetry.
    """
    def __init__(self):
        super(EEGNet, self).__init__()
        
        # ==========================================
        # 1. TEMPORAL BLOCK (Bandpass Filter)
        # ==========================================
        # Acts as a set of digital bandpass filters. The kernel_size=(1, 32) slides 
        # across the time axis to extract frequency-specific features (like Alpha/Beta waves) 
        # independently for each channel before mixing them.
        self.temporal = nn.Sequential(
            nn.Conv2d(1, 16, kernel_size=(1, 32), padding=(0, 16), bias=False),
            nn.BatchNorm2d(16)
        )
        
        # ==========================================
        # 2. SPATIAL BLOCK (Electrode Topography)
        # ==========================================
        # Learns spatial patterns across the 8 EEG electrodes. 
        # kernel_size=(8, 1) spans all 8 channels at a single point in time.
        # 'groups=16' ensures it acts as a Depthwise Convolution, applying filters 
        # to each temporal feature map independently.
        self.spatial = nn.Sequential(
            nn.Conv2d(16, 32, kernel_size=(8, 1), groups=16, bias=False),
            nn.BatchNorm2d(32), 
            nn.ELU(),  # Exponential Linear Unit handles negative signal dips better than ReLU
            nn.AvgPool2d((1, 4)), 
            nn.Dropout(0.3) # Regularization: Prevents the AI from memorizing a specific subject
        )
        
        # ==========================================
        # 3. SEPARABLE BLOCK (Feature Fusion)
        # ==========================================
        # Separable convolution (Depthwise + Pointwise) optimally merges the temporal 
        # and spatial features together. This block reduces the computational load by 
        # roughly 80% compared to a standard convolution layer.
        self.separable = nn.Sequential(
            nn.Conv2d(32, 32, kernel_size=(1, 16), padding=(0, 8), groups=32, bias=False),
            nn.Conv2d(32, 32, kernel_size=1, bias=False),
            nn.BatchNorm2d(32), 
            nn.ELU(),
            nn.AvgPool2d((1, 8)), 
            nn.Dropout(0.3)
        )
        
        # ==========================================
        # 4. CLASSIFIER (Psychological Output)
        # ==========================================
        # Flattens the abstract 2D feature maps into a 1D array, then passes them 
        # through dense layers to output the final 2 coordinates for Russell's Circumplex.
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(32 * 1 * 4, 64),
            nn.ReLU(),
            nn.Linear(64, 2)  # Output: [Valence_Logit, Arousal_Logit]
        )

    def forward(self, x):
        """
        The Forward Pass. Pushes the raw tensor through the network blocks sequentially.
        Input Shape: (Batch_Size, 1, Channels=8, Time_Samples=128)
        Output Shape: (Batch_Size, 2)
        """
        return self.classifier(self.separable(self.spatial(self.temporal(x))))